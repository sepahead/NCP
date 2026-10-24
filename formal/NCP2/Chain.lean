/-
The accepted history of a session is a hash chain (spec 7.7, properties 2, 3, and 6).
-/
import NCP2.Model

namespace NCP2

variable (H : Frame → Id)

/-- The request and response frames of a list of exchanges. -/
def frames (xs : List Exchange) : List Frame :=
  xs.flatMap fun x => [.req x.request, .resp x.response]

/-- `Chain H xs y`: `xs` is the accepted history of a session, `open` first, and `y` is its last
exchange. Each later request carries the next sequence number and acknowledges the identity of the
response before it; each response names the identity of its request; and nothing follows an
exchange that ends the session. -/
inductive Chain : List Exchange → Exchange → Prop
  | start (x : Exchange)
      (hop : x.request.op = .openSession) (hack : x.request.ack = none)
      (hseq : x.request.seq = 0) (hreq : x.response.request = H (.req x.request)) :
      Chain [x] x
  | extend (xs : List Exchange) (y x : Exchange) (hc : Chain xs y)
      (hseq : x.request.seq = xs.length)
      (hack : x.request.ack = some (H (.resp y.response)))
      (hreq : x.response.request = H (.req x.request))
      (hop : x.request.op ≠ .openSession)
      (hlive : ¬ Ends y) :
      Chain (xs ++ [x]) x

variable {H}

theorem frames_append (xs ys : List Exchange) : frames (xs ++ ys) = frames xs ++ frames ys := by
  simp [frames, List.flatMap_append]

theorem Chain.last_frames {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    Frame.req y.request ∈ frames xs ∧ Frame.resp y.response ∈ frames xs := by
  cases hc <;> simp [frames]

theorem Chain.last_req {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    y.response.request = H (.req y.request) := by
  cases hc <;> assumption

theorem Chain.ne_nil {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) : xs ≠ [] := by
  cases hc <;> simp

theorem Chain.getLast {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    xs.getLast? = some y := by
  cases hc <;> simp

/-- Properties 1 and 2: the sequence numbers of the accepted requests are 0, 1, 2, ..., so each
sequence number, and hence each request, is executed at most once and without gaps. -/
theorem Chain.seqs {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    xs.map (·.request.seq) = List.range xs.length := by
  induction hc with
  | start x _ _ hseq _ => simp [hseq]
  | extend xs y x _ hseq _ _ _ _ ih => simp [List.range_succ, ih, hseq]

theorem Chain.requests_nodup {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    (xs.map (·.request)).Nodup := by
  have h := hc.seqs
  have hn : (xs.map (·.request.seq)).Nodup := by rw [h]; exact List.nodup_range
  rw [show xs.map (·.request.seq) = (xs.map (·.request)).map (·.seq) by simp] at hn
  exact List.Pairwise.of_map (·.seq) (fun a b h hab => h (by rw [hab])) hn

private theorem exchange_eq {x y : Exchange} (hq : x.request = y.request)
    (hp : x.response = y.response) : x = y := by
  cases x; cases y; simp_all

/-- Property 6: the identity of the last response commits to the whole accepted history. If `H`
has no collision among the frames of two histories, equal identities of their last responses
imply equal histories. -/
theorem Chain.unique {xs ys : List Exchange} {x y : Exchange}
    (hx : Chain H xs x) (hy : Chain H ys y)
    (hinj : ∀ f ∈ frames xs, ∀ g ∈ frames ys, H f = H g → f = g)
    (h : H (.resp x.response) = H (.resp y.response)) : xs = ys := by
  induction hx generalizing ys y with
  | start x hop hack hseq hreq =>
    have hp : x.response = y.response := by
      have := hinj _ (by simp [frames]) _ hy.last_frames.2 h
      injection this
    have hq : x.request = y.request := by
      have hrid : H (.req x.request) = H (.req y.request) := by
        rw [← hreq, ← hy.last_req, hp]
      have := hinj _ (by simp [frames]) _ hy.last_frames.1 hrid
      injection this
    cases hy with
    | start => simp [exchange_eq hq hp]
    | extend ys' w y' _ _ hack' _ _ _ => rw [← hq, hack] at hack'; cases hack'
  | extend xs z x hc hseq hack hreq hop hlive ih =>
    have hxmem : Frame.req x.request ∈ frames (xs ++ [x]) ∧
        Frame.resp x.response ∈ frames (xs ++ [x]) := by simp [frames]
    have hp : x.response = y.response := by
      have := hinj _ hxmem.2 _ hy.last_frames.2 h
      injection this
    have hq : x.request = y.request := by
      have hrid : H (.req x.request) = H (.req y.request) := by
        rw [← hreq, ← hy.last_req, hp]
      have := hinj _ hxmem.1 _ hy.last_frames.1 hrid
      injection this
    cases hy with
    | start _ _ hack' _ _ => rw [← hq, hack] at hack'; cases hack'
    | extend ys' w y' hc' _ hack' _ _ _ =>
      rw [← hq, hack] at hack'
      injection hack' with hzw
      have hsub : ∀ f ∈ frames xs, ∀ g ∈ frames ys', H f = H g → f = g := by
        intro f hf g hg
        exact hinj f (by simp [frames_append, hf]) g (by simp [frames_append, hg])
      rw [ih hc' hsub hzw, exchange_eq hq hp]

theorem Chain.getElem_last {xs : List Exchange} {y : Exchange} (hc : Chain H xs y)
    (h : xs.length - 1 < xs.length) : xs[xs.length - 1] = y := by
  cases hc <;> simp

/-- Property 3, by position: request `i + 1` acknowledges the identity of response `i`. -/
theorem Chain.ack_index {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    ∀ (i : Nat) (h : i + 1 < xs.length), xs[i + 1].request.ack = some (H (.resp xs[i].response)) := by
  induction hc with
  | start x _ _ _ _ => intro i h; simp at h
  | extend xs y x hc _ hack _ _ _ ih =>
    intro i h
    simp only [List.length_append, List.length_singleton] at h
    by_cases hi : i + 1 < xs.length
    · rw [List.getElem_append_left hi, List.getElem_append_left (by omega)]
      exact ih i hi
    · have hi' : i + 1 = xs.length := by omega
      have hlast : xs[i]'(by omega) = y := by
        have := hc.getElem_last (by have := hc.ne_nil; cases xs <;> simp_all)
        simpa [show xs.length - 1 = i by omega] using this
      have e1 : (xs ++ [x])[i + 1] = x := by simp [hi']
      have e2 : (xs ++ [x])[i] = y := by rw [List.getElem_append_left (by omega)]; exact hlast
      rw [e1, e2, hack]

/-- Property 7, by position: no exchange before the last ends the session. -/
theorem Chain.live_index {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    ∀ (i : Nat) (h : i + 1 < xs.length), ¬ Ends xs[i] := by
  induction hc with
  | start x _ _ _ _ => intro i h; simp at h
  | extend xs y x hc _ _ _ _ hlive ih =>
    intro i h
    simp only [List.length_append, List.length_singleton] at h
    rw [List.getElem_append_left (by omega)]
    by_cases hi : i + 1 < xs.length
    · exact ih i hi
    · have hlast : xs[i]'(by omega) = y := by
        have := hc.getElem_last (by have := hc.ne_nil; cases xs <;> simp_all)
        simpa [show xs.length - 1 = i by omega] using this
      rw [hlast]; exact hlive

end NCP2
