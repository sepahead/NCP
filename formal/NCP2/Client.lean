/-
What a client can conclude from a response (spec 7.4, 7.5, and 7.7, properties 4 and 5).

The argument is compositional. A network can lose, repeat, delay, or reorder frames, but it cannot
make a response that the owner did not send, under two assumptions: changed frames are detected
(by the digest check, or because the binding is a reliable stream), and no third party sends frames
with valid digests (a digest is not an authentication code; the binding authenticates the peer).
Under them it is enough to know what each response that the owner sends says about its history.
-/
import NCP2.Owner

namespace NCP2

variable {H : Frame → Id} {app : App}

theorem mem_eq_of_nodup_map {α β : Type} {f : α → β} :
    ∀ {xs : List α}, (xs.map f).Nodup → ∀ {x y : α}, x ∈ xs → y ∈ xs → f x = f y → x = y
  | [], _, _, _, hx, _, _ => by cases hx
  | z :: zs, h, x, y, hx, hy, hf => by
    rw [List.map_cons, List.nodup_cons] at h
    have notin : ∀ w ∈ zs, f w ≠ f z := fun w hw hwz => h.1 (hwz ▸ List.mem_map_of_mem hw)
    rcases List.mem_cons.1 hx with rfl | hx' <;> rcases List.mem_cons.1 hy with rfl | hy'
    · rfl
    · exact absurd hf.symm (notin y hy')
    · exact absurd hf (notin x hx')
    · exact mem_eq_of_nodup_map h.2 hx' hy' hf

theorem Chain.resp_req {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    ∀ x ∈ xs, x.response.request = H (.req x.request) := by
  induction hc with
  | start x _ _ _ hreq => intro z hz; simp at hz; subst hz; exact hreq
  | extend xs y x _ _ _ hreq _ _ ih =>
    intro z hz
    rcases List.mem_append.1 hz with hz | hz
    · exact ih z hz
    · simp at hz; subst hz; exact hreq

theorem Chain.seq_nodup {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    (xs.map (·.request.seq)).Nodup := by
  rw [hc.seqs]; exact List.nodup_range

/-- The accepted history only grows: every step keeps it as a prefix. -/
theorem step_log_prefix {o : Owner} (hinv : Inv H o) (r : Request) (a : Behavior) :
    o.log <+: (step H app o r a).1.log := by
  unfold step
  split
  · exact List.prefix_refl _
  split
  · rename_i hnone
    rcases hinv with ⟨_, hl, _⟩ | ⟨s, _, hs, _⟩
    · unfold openStep
      repeat' split
      all_goals first | exact List.prefix_refl _ | simp [hl]
    · rw [hs] at hnone; cases hnone
  · split
    · exact List.prefix_refl _
    split
    · split
      · split <;> exact List.prefix_refl _
      · unfold checkThenAccept
        repeat' split
        all_goals first | exact List.prefix_refl _ | simp [accept]
    · unfold checkThenAccept
      repeat' split
      all_goals first | exact List.prefix_refl _ | simp [accept]

/-- Every response that is not `rejected` is the response of an exchange in the history. -/
theorem step_response_logged {o : Owner} (hinv : Inv H o) (r : Request) (a : Behavior)
    (h : (step H app o r a).2.outcome ≠ .rejected) :
    ∃ x ∈ (step H app o r a).1.log, x.response = (step H app o r a).2 := by
  revert h
  unfold step
  split
  · intro h; exact (h (by simp [reject, reply])).elim
  split
  · unfold openStep
    repeat' split
    all_goals first | (intro _; exact ⟨_, List.mem_singleton_self _, rfl⟩) | (intro h; exact (h (by simp [reject, reply])).elim)
  · rename_i s' hs'
    rcases hinv with ⟨hn, _, _⟩ | ⟨s, y, hs, hc, hk, _⟩
    · rw [hn] at hs'; cases hs'
    split
    · intro h; exact (h (by simp [reject, reply])).elim
    split
    · rename_i k hk'
      rw [hk] at hk'; cases hk'
      split
      · split
        · intro; exact ⟨y, hc.last_mem, rfl⟩
        · intro h; exact (h (by simp [reject, reply])).elim
      · unfold checkThenAccept
        repeat' split
        all_goals first | (intro _; exact ⟨_, List.mem_append_right _ (List.mem_singleton_self _), rfl⟩) | (intro h; exact (h (by simp [reject, reply])).elim)
    · unfold checkThenAccept
      repeat' split
      all_goals first | (intro _; exact ⟨_, List.mem_append_right _ (List.mem_singleton_self _), rfl⟩) | (intro h; exact (h (by simp [reject, reply])).elim)

/-- Every rejection except `seq_stale` means that the owner has never executed the request. -/
theorem step_rejected_not_logged {o : Owner} (hinv : Inv H o) (r : Request) (a : Behavior)
    (hrej : (step H app o r a).2.outcome = .rejected)
    (hcode : (step H app o r a).2.code ≠ some .seqStale) :
    r ∉ o.log.map (·.request) := by
  intro hmem
  obtain ⟨x, hx, rfl⟩ := List.mem_map.1 hmem
  rcases hinv with ⟨_, hl, _⟩ | ⟨s, y, hs, hc, hk, hh, _, hl⟩
  · rw [hl] at hx; cases hx
  obtain ⟨hsess, hprot, _⟩ := hl x hx
  have hseqle : x.request.seq ≤ o.high := by
    have hin : x.request.seq ∈ List.range o.log.length := by
      rw [← hc.seqs]; exact List.mem_map_of_mem hx
    have := hc.last_seq
    simp at hin; omega
  have hstep : step H app o x.request a =
      if x.request.seq = o.high then
        (if H (.req x.request) = H (.req y.request) then (o, y.response)
         else (o, reject H x.request .seqConflict))
      else checkThenAccept H app o (some (H (.resp y.response))) x.request a := by
    unfold step; simp [hprot, hs, hsess, hk]
  rw [hstep] at hrej hcode
  split at hrej
  · rename_i heq
    split at hrej
    · exact (hl y hc.last_mem).2.2 hrej
    · rename_i hne
      have hxy : x = y := mem_eq_of_nodup_map hc.seq_nodup hx hc.last_mem (by simp [heq, hh])
      exact hne (by rw [hxy])
  · rename_i hne
    simp only [hne, ↓reduceIte] at hcode
    unfold checkThenAccept at hcode
    split at hcode
    · simp [reject, reply] at hcode
    · rename_i hlt; omega

/-- For every digest `H`, a delayed copy of an executed request is rejected with `seq_stale` once a
later request has executed. So `seq_stale` says that this frame executed nothing, not that the
request never executed. The requests acknowledge the real identities `H (.resp p0)` and
`H (.resp p1)`, so the run is a correct one for any digest. -/
theorem seqStale_after_execution (H : Frame → Id) :
    let app : App := { known := fun _ => true, opening := fun _ => .accept 65536 }
    let r0 : Request := { protocol := 2, session := 1, seq := 0, op := .openSession, ack := none, body := 0 }
    let p0 := reply H r0 .ok none (.opened 65536)
    let r1 : Request :=
      { protocol := 2, session := 1, seq := 1, op := .call 0, ack := some (H (.resp p0)), body := 0 }
    let p1 := reply H r1 .ok none (.result 1)
    let r2 : Request :=
      { protocol := 2, session := 1, seq := 2, op := .call 0, ack := some (H (.resp p1)), body := 1 }
    let o := run H app {} [(r0, ⟨true, .result 0⟩), (r1, ⟨true, .result 1⟩), (r2, ⟨true, .result 2⟩)]
    (step H app o r1 ⟨true, .result 1⟩).2.code = some .seqStale ∧ r1 ∈ o.log.map (·.request) := by
  simp [run, step, openStep, checkThenAccept, accept, execute, reply, reject, Ends]

/-- The responses that the owner sends during a sequence of requests. -/
def responses (H : Frame → Id) (app : App) (o : Owner) : List (Request × Behavior) → List Response
  | [] => []
  | (r, a) :: rest => (step H app o r a).2 :: responses H app (step H app o r a).1 rest

theorem inv_run_from {o : Owner} (hinv : Inv H o) (inputs : List (Request × Behavior)) :
    Inv H (run H app o inputs) := by
  induction inputs generalizing o with
  | nil => exact hinv
  | cons x rest ih => exact ih (inv_step hinv x.1 x.2)

theorem run_log_prefix {o : Owner} (hinv : Inv H o) (inputs : List (Request × Behavior)) :
    o.log <+: (run H app o inputs).log := by
  induction inputs generalizing o with
  | nil => exact List.prefix_refl _
  | cons x rest ih => exact (step_log_prefix hinv x.1 x.2).trans (ih (inv_step hinv x.1 x.2))

/-- Every response that the owner sends and that is not `rejected` belongs to an exchange in the
history at every later time. -/
theorem responses_logged {o : Owner} (hinv : Inv H o) (inputs : List (Request × Behavior))
    {p : Response} (hp : p ∈ responses H app o inputs) (hnr : p.outcome ≠ .rejected) :
    ∃ x ∈ (run H app o inputs).log, x.response = p := by
  induction inputs generalizing o with
  | nil => cases hp
  | cons x rest ih =>
    rcases List.mem_cons.1 hp with rfl | hp'
    · obtain ⟨z, hz, hzp⟩ := step_response_logged hinv x.1 x.2 hnr
      exact ⟨z, (run_log_prefix (inv_step hinv x.1 x.2) rest).subset hz, hzp⟩
    · exact ih (inv_step hinv x.1 x.2) hp'

/-- A step adds to the history only the request that it handles. -/
theorem step_log_sub {o : Owner} (r : Request) (a : Behavior) :
    ∀ x ∈ (step H app o r a).1.log, x ∈ o.log ∨ x.request = r := by
  unfold step
  split
  · intro x hx; exact Or.inl hx
  split
  · unfold openStep
    repeat' split
    all_goals first
      | (intro x hx; exact Or.inl hx)
      | (intro x hx; simp at hx; subst hx; exact Or.inr rfl)
  · split
    · intro x hx; exact Or.inl hx
    split
    · split
      · split <;> (intro x hx; exact Or.inl hx)
      · unfold checkThenAccept
        repeat' split
        all_goals first
          | (intro x hx; exact Or.inl hx)
          | (intro x hx
             simp only [accept, List.mem_append, List.mem_singleton] at hx
             rcases hx with hx | rfl
             · exact Or.inl hx
             · exact Or.inr rfl)
    · unfold checkThenAccept
      repeat' split
      all_goals first
        | (intro x hx; exact Or.inl hx)
        | (intro x hx
           simp only [accept, List.mem_append, List.mem_singleton] at hx
           rcases hx with hx | rfl
           · exact Or.inl hx
           · exact Or.inr rfl)

/-- The history contains only requests that the owner received. -/
theorem run_log_sub {o : Owner} (inputs : List (Request × Behavior)) :
    ∀ x ∈ (run H app o inputs).log, x ∈ o.log ∨ x.request ∈ inputs.map (·.1) := by
  induction inputs generalizing o with
  | nil => intro x hx; exact Or.inl hx
  | cons i rest ih =>
    obtain ⟨r, b⟩ := i
    intro x hx
    simp only [run] at hx
    rcases ih x hx with h | h
    · rcases step_log_sub r b x h with h' | h'
      · exact Or.inl h'
      · exact Or.inr (by simp [h'])
    · exact Or.inr (by simp [h])

/-- Property 4: an `ok` response that the owner sent and that names the identity of the client's
request `r` is the response of exactly one execution of `r`, if no other request in the history
shares `r`'s identity. The assumption concerns only frames of the run, so a collision-resistant
digest such as SHA-256 can satisfy it. Under the assumptions in the header, this covers every
network. -/
theorem ok_is_own_execution {o : Owner} (hinv : Inv H o) (inputs : List (Request × Behavior))
    {p : Response} {r : Request} (hp : p ∈ responses H app o inputs) (hok : p.outcome = .ok)
    (hreq : p.request = H (.req r))
    (hinj : ∀ q ∈ (run H app o inputs).log.map (·.request), H (.req q) = H (.req r) → q = r) :
    ∃ x ∈ (run H app o inputs).log, x.request = r ∧ x.response = p ∧
      ∀ x' ∈ (run H app o inputs).log, x'.request = r → x' = x := by
  obtain ⟨x, hx, hxp⟩ := responses_logged hinv inputs hp (by simp [hok])
  rcases inv_run_from (app := app) hinv inputs with ⟨_, hl, _⟩ | ⟨s, y, _, hc, _⟩
  · rw [hl] at hx; cases hx
  have hxr : x.request = r :=
    hinj _ (List.mem_map_of_mem hx) (by rw [← hc.resp_req x hx, hxp, hreq])
  refine ⟨x, hx, hxr, hxp, fun x' hx' hx'r => ?_⟩
  have hnodup := hc.requests_nodup
  exact mem_eq_of_nodup_map hnodup hx' hx (by simp [hx'r, hxr])

end NCP2
