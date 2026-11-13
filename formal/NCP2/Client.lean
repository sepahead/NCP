/-
What a client can conclude from a response (spec 7.4, 7.5, and 7.7, properties 4 to 6).

The argument is compositional. A network can lose, repeat, delay, or reorder frames, but it cannot
make a response that the owner did not send, under two assumptions: changed frames are detected
(by the digest check, or because the binding is a reliable stream), and no third party sends frames
with valid digests (a digest is not an authentication code; the binding or authenticated frames
authenticate the peer). Under them it is enough to know what each response that the owner sends
says about its history, now and at every later time.
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

theorem Chain.seq_nodup {xs : List Exchange} {y : Exchange} (hc : Chain H xs y) :
    (xs.map (·.request.seq)).Nodup := by
  rw [hc.seqs]; exact List.nodup_range

theorem run_append (o : Owner) (a b : List Input) :
    run H app o (a ++ b) = run H app (run H app o a) b := by
  induction a generalizing o with
  | nil => rfl
  | cons i rest ih => exact ih _

/-- The admitted history only grows: every step keeps it as a prefix. -/
theorem step_log_prefix {o : Owner} (hinv : Inv H o) (r : Request) (b : Behavior) :
    o.log <+: (step H app o r b).1.log := by
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
      · unfold checkThenAdmit
        repeat' split
        all_goals first | exact List.prefix_refl _ | simp [admit]
    · unfold checkThenAdmit
      repeat' split
      all_goals first | exact List.prefix_refl _ | simp [admit]

theorem apply_log_prefix {o : Owner} (hinv : Inv H o) (i : Input) :
    o.log <+: (apply H app o i).log := by
  cases i with
  | req r b => exact step_log_prefix hinv r b
  | stop => exact List.prefix_refl _

theorem run_log_prefix {o : Owner} (hinv : Inv H o) (inputs : List Input) :
    o.log <+: (run H app o inputs).log := by
  induction inputs generalizing o with
  | nil => exact List.prefix_refl _
  | cons i rest ih => exact (apply_log_prefix hinv i).trans (ih (inv_apply hinv i))

/-- Every keepable response is the response of an exchange in the history. -/
theorem step_response_logged {o : Owner} (hinv : Inv H o) (r : Request) (b : Behavior)
    (h : Keepable (step H app o r b).2) :
    ∃ x ∈ (step H app o r b).1.log, x.response = (step H app o r b).2 := by
  revert h
  unfold step
  split
  · intro h; simp [Keepable, reject, reply] at h
  split
  · unfold openStep
    repeat' split
    all_goals first
      | (intro _; exact ⟨_, List.mem_singleton_self _, rfl⟩)
      | (intro h; simp [Keepable, reject, reply] at h; done)
  · rename_i s' hs'
    rcases hinv with ⟨hn, _, _⟩ | ⟨s, y, hs, hc, hk, _⟩
    · rw [hn] at hs'; cases hs'
    split
    · intro h; simp [Keepable, reject, reply] at h
    split
    · rename_i k hk'
      rw [hk] at hk'; cases hk'
      split
      · split
        · intro; exact ⟨y, hc.last_mem, rfl⟩
        · intro h; simp [Keepable, reject, reply] at h
      · unfold checkThenAdmit admit
        repeat' split
        all_goals first
          | (intro _; exact ⟨_, List.mem_append_right _ (List.mem_singleton_self _), rfl⟩)
          | (intro h; simp [Keepable, reject, reply] at h; done)
    · unfold checkThenAdmit admit
      repeat' split
      all_goals first
        | (intro _; exact ⟨_, List.mem_append_right _ (List.mem_singleton_self _), rfl⟩)
        | (intro h; simp [Keepable, reject, reply] at h; done)

/-- Every keepable response that the owner sends belongs to an exchange in the history at every
later time. -/
theorem responses_logged {o : Owner} (hinv : Inv H o) (inputs : List Input)
    {p : Response} (hp : p ∈ responses H app o inputs) (hk : Keepable p) :
    ∃ x ∈ (run H app o inputs).log, x.response = p := by
  induction inputs generalizing o with
  | nil => cases hp
  | cons i rest ih =>
    cases i with
    | req r b =>
      rcases List.mem_cons.1 hp with rfl | hp'
      · obtain ⟨z, hz, hzp⟩ := step_response_logged hinv r b hk
        exact ⟨z, (run_log_prefix (inv_step hinv r b) rest).subset hz, hzp⟩
      · exact ih (inv_step hinv r b) hp'
    | stop => exact ih (inv_stop hinv) hp

/-- A response with outcome `ok` or `declined` is keepable: only `ended` responses admit nothing
besides rejections. -/
theorem step_keepable {o : Owner} (hinv : Inv H o) (r : Request) (b : Behavior)
    (h : (step H app o r b).2.outcome = .ok ∨ (step H app o r b).2.outcome = .declined) :
    Keepable (step H app o r b).2 := by
  revert h
  unfold step
  split
  · simp [reject, reply]
  split
  · unfold openStep
    repeat' split
    all_goals simp [reject, reply, Keepable]
  · rename_i s₀ hs₀
    rcases hinv with ⟨hn, _, _⟩ | ⟨s, y, hs, hc, hk, _, _, hl⟩
    · rw [hn] at hs₀; cases hs₀
    split
    · simp [reject, reply]
    split
    · rename_i k hk'
      rw [hk] at hk'; cases hk'
      split
      · split
        · intro; exact (hl y hc.last_mem).2.2
        · simp [reject, reply]
      · unfold checkThenAdmit admit
        repeat' split
        all_goals first
          | (intro; exact answer_keepable _ _ _)
          | simp [reject, reply]
    · unfold checkThenAdmit admit
      repeat' split
      all_goals first
        | (intro; exact answer_keepable _ _ _)
        | simp [reject, reply]

theorem responses_keepable {o : Owner} (hinv : Inv H o) (inputs : List Input) {p : Response}
    (hp : p ∈ responses H app o inputs) (h : p.outcome = .ok ∨ p.outcome = .declined) :
    Keepable p := by
  induction inputs generalizing o with
  | nil => cases hp
  | cons i rest ih =>
    cases i with
    | req r b =>
      rcases List.mem_cons.1 hp with rfl | hp'
      · exact step_keepable hinv r b h
      · exact ih (inv_step hinv r b) hp'
    | stop => exact ih (inv_stop hinv) hp

/-- Every rejection except `seq_stale` means that the owner has never admitted the request. -/
theorem step_rejected_not_logged {o : Owner} (hinv : Inv H o) (r : Request) (a : Behavior)
    (hrej : (step H app o r a).2.outcome = .rejected)
    (hcode : (step H app o r a).2.code ≠ some .seqStale) :
    r ∉ o.log.map (·.request) := by
  intro hmem
  obtain ⟨x, hx, rfl⟩ := List.mem_map.1 hmem
  rcases hinv with ⟨_, hl, _⟩ | ⟨s, y, hs, hc, hk, hh, _, hl⟩
  · rw [hl] at hx; cases hx
  obtain ⟨hsess, hprot, hkeep⟩ := hl x hx
  have hseqle : x.request.seq ≤ o.high := by
    have hin : x.request.seq ∈ List.range o.log.length := by
      rw [← hc.seqs]; exact List.mem_map_of_mem hx
    have := hc.last_seq
    simp at hin; omega
  have hstep : step H app o x.request a =
      if x.request.seq = o.high then
        (if H (.req x.request) = H (.req y.request) then (o, y.response)
         else (o, reject H x.request .seqConflict))
      else checkThenAdmit H app o (some (H (.resp y.response))) x.request a := by
    unfold step; simp [hprot, hs, hsess, hk]
  rw [hstep] at hrej hcode
  split at hrej
  · rename_i heq
    split at hrej
    · exact (hl y hc.last_mem).2.2.1 hrej
    · rename_i hne
      have hxy : x = y := mem_eq_of_nodup_map hc.seq_nodup hx hc.last_mem (by simp [heq, hh])
      exact hne (by rw [hxy])
  · rename_i hne
    simp only [hne, ↓reduceIte] at hcode
    unfold checkThenAdmit at hcode
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
    let p0 := reply H r0 .ok none (.opened 65536 0)
    let r1 : Request :=
      { protocol := 2, session := 1, seq := 1, op := .call 0, ack := some (H (.resp p0)), body := 0 }
    let p1 := reply H r1 .ok none (.result 1)
    let r2 : Request :=
      { protocol := 2, session := 1, seq := 2, op := .call 0, ack := some (H (.resp p1)), body := 1 }
    let o := run H app {} [.req r0 ⟨true, .result 0, 0⟩, .req r1 ⟨true, .result 1, 0⟩,
                           .req r2 ⟨true, .result 2, 0⟩]
    (step H app o r1 ⟨true, .result 1, 0⟩).2.code = some .seqStale ∧
      ∃ x ∈ o.log, x.request = r1 ∧ Executed x := by
  simp [run, apply, step, openStep, checkThenAdmit, admit, answer, reply, reject, Ends, Executed]

/-- A step adds to the history only the request that it handles. -/
theorem step_log_sub {o : Owner} (r : Request) (b : Behavior) :
    ∀ x ∈ (step H app o r b).1.log, x ∈ o.log ∨ x.request = r := by
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
      · unfold checkThenAdmit
        repeat' split
        all_goals first
          | (intro x hx; exact Or.inl hx)
          | (intro x hx
             simp only [admit, List.mem_append, List.mem_singleton] at hx
             rcases hx with hx | rfl
             · exact Or.inl hx
             · exact Or.inr rfl)
    · unfold checkThenAdmit
      repeat' split
      all_goals first
        | (intro x hx; exact Or.inl hx)
        | (intro x hx
           simp only [admit, List.mem_append, List.mem_singleton] at hx
           rcases hx with hx | rfl
           · exact Or.inl hx
           · exact Or.inr rfl)

/-- The history contains only requests that the owner received. -/
theorem run_log_sub {o : Owner} (inputs : List Input) :
    ∀ x ∈ (run H app o inputs).log, x ∈ o.log ∨ x.request ∈ requests inputs := by
  induction inputs generalizing o with
  | nil => intro x hx; exact Or.inl hx
  | cons i rest ih =>
    cases i with
    | req r b =>
      intro x hx
      rcases ih x hx with h | h
      · rcases step_log_sub r b x h with h' | h'
        · exact Or.inl h'
        · exact Or.inr (by simp [requests, h'])
      · exact Or.inr (by simp [requests, h])
    | stop =>
      intro x hx
      rcases ih x hx with h | h
      · exact Or.inl h
      · exact Or.inr h

/-- Property 4: an `ok` response that the owner sent and that names the identity of the client's
request `r` is the response of exactly one execution of `r`, if no other request in the history
shares `r`'s identity. Under the assumptions in the header, this covers every network. -/
theorem ok_is_own_execution {o : Owner} (hinv : Inv H o) (inputs : List Input)
    {p : Response} {r : Request} (hp : p ∈ responses H app o inputs) (hok : p.outcome = .ok)
    (hreq : p.request = H (.req r))
    (hinj : ∀ q ∈ (run H app o inputs).log.map (·.request), H (.req q) = H (.req r) → q = r) :
    ∃ x ∈ (run H app o inputs).log, x.request = r ∧ x.response = p ∧
      ∀ x' ∈ (run H app o inputs).log, x'.request = r → x' = x := by
  obtain ⟨x, hx, hxp⟩ :=
    responses_logged hinv inputs hp (responses_keepable hinv inputs hp (Or.inl hok))
  rcases inv_run_from (app := app) hinv inputs with ⟨_, hl, _⟩ | ⟨s, y, _, hc, _⟩
  · rw [hl] at hx; cases hx
  have hxr : x.request = r :=
    hinj _ (List.mem_map_of_mem hx) (by rw [← hc.resp_req x hx, hxp, hreq])
  refine ⟨x, hx, hxr, hxp, fun x' hx' hx'r => ?_⟩
  exact mem_eq_of_nodup_map hc.requests_nodup hx' hx (by simp [hx'r, hxr])

/-- A keepable response that the owner sent for request `r` stays the only exchange of `r` in
every later history: the answer to an admitted request never changes. -/
theorem kept_is_final {o : Owner} (hinv : Inv H o) (inputs more : List Input)
    {p : Response} {r : Request} (hp : p ∈ responses H app o inputs) (hk : Keepable p)
    (hreq : p.request = H (.req r))
    (hinj : ∀ q ∈ (run H app o (inputs ++ more)).log.map (·.request),
      H (.req q) = H (.req r) → q = r) :
    ∃ x ∈ (run H app o (inputs ++ more)).log, x.request = r ∧ x.response = p ∧
      ∀ x' ∈ (run H app o (inputs ++ more)).log, x'.request = r → x' = x := by
  obtain ⟨x, hx, hxp⟩ := responses_logged hinv inputs hp hk
  have hlater : x ∈ (run H app o (inputs ++ more)).log := by
    rw [run_append]
    exact (run_log_prefix (inv_run_from hinv inputs) more).subset hx
  rcases inv_run_from (app := app) hinv (inputs ++ more) with ⟨_, hl, _⟩ | ⟨s, y, _, hc, _⟩
  · rw [hl] at hlater; cases hlater
  have hxr : x.request = r :=
    hinj _ (List.mem_map_of_mem hlater) (by rw [← hc.resp_req x hlater, hxp, hreq])
  refine ⟨x, hlater, hxr, hxp, fun x' hx' hx'r => ?_⟩
  exact mem_eq_of_nodup_map hc.requests_nodup hx' hlater (by simp [hx'r, hxr])

/-- Property 5: a request that the owner declined never executes, at any later time. -/
theorem declined_is_final {o : Owner} (hinv : Inv H o) (inputs more : List Input)
    {p : Response} {r : Request} (hp : p ∈ responses H app o inputs) (hd : p.outcome = .declined)
    (hreq : p.request = H (.req r))
    (hinj : ∀ q ∈ (run H app o (inputs ++ more)).log.map (·.request),
      H (.req q) = H (.req r) → q = r) :
    ∀ x ∈ (run H app o (inputs ++ more)).log, x.request = r → ¬ Executed x := by
  intro x hx hxr
  obtain ⟨y, _, _, hyp, huniq⟩ :=
    kept_is_final hinv inputs more hp (responses_keepable hinv inputs hp (Or.inr hd)) hreq hinj
  rw [huniq x hx hxr]
  simp [Executed, hyp, hd]

/-- The `shutdown` branch: the owner stops, admits nothing, has not admitted the request, and the
response names it. -/
theorem step_shutdown {o : Owner} (hinv : Inv H o) (r : Request) (b : Behavior)
    (h : (step H app o r b).2.code = some .shutdown) :
    o.stopped = true ∧ (step H app o r b).1 = o ∧ r ∉ o.log.map (·.request) ∧
      (step H app o r b).2.request = H (.req r) := by
  revert h
  unfold step
  split
  · simp [reject, reply]
  split
  · unfold openStep
    repeat' split
    all_goals simp [reject, reply]
  · rename_i s₀ hs₀
    rcases hinv with ⟨hn, _, _⟩ | ⟨s, y, hs, hc, hk, hh, _, hl⟩
    · rw [hn] at hs₀; cases hs₀
    split
    · simp [reject, reply]
    split
    · rename_i k hk'
      rw [hk] at hk'; cases hk'
      split
      · split
        · intro h; exact ((hl y hc.last_mem).2.2.2.2 h).elim
        · simp [reject, reply]
      · unfold checkThenAdmit
        split
        · simp [reject, reply]
        split
        · simp [reject, reply]
        split
        · simp [reject, reply]
        rename_i hlt hgt _
        split
        · simp [reject, reply]
        split
        · simp [reject, reply]
        split
        · simp [reject, reply]
        split
        · rename_i hstop
          intro _
          refine ⟨hstop, rfl, ?_, rfl⟩
          intro hmem
          obtain ⟨x, hx, rfl⟩ := List.mem_map.1 hmem
          have hin : x.request.seq ∈ List.range o.log.length := by
            rw [← hc.seqs]; exact List.mem_map_of_mem hx
          have := hc.last_seq
          simp at hin; omega
        · intro h
          exact ((answer_keepable (H := H) (app := app) o.bound r b).2.2 (by simpa [admit] using h)).elim
    · rename_i hk'; rw [hk] at hk'; cases hk'

/-- Property 5: a request that got `shutdown` is never admitted, at any later time, if no other
request among the inputs shares its identity. -/
theorem shutdown_is_final {o : Owner} (hinv : Inv H o) (inputs more : List Input)
    {p : Response} {r : Request} (hp : p ∈ responses H app o inputs) (hs : p.code = some .shutdown)
    (hreq : p.request = H (.req r))
    (hinj : ∀ q ∈ requests (inputs ++ more), H (.req q) = H (.req r) → q = r) :
    r ∉ (run H app o (inputs ++ more)).log.map (·.request) := by
  induction inputs generalizing o with
  | nil => cases hp
  | cons i rest ih =>
    cases i with
    | stop =>
      exact ih (inv_stop hinv) hp (fun q hq => hinj q (by simpa [requests] using hq))
    | req r' b =>
      rcases List.mem_cons.1 hp with rfl | hp'
      · obtain ⟨hstop, hsame, hnot, hname⟩ := step_shutdown hinv r' b hs
        have hr : r' = r := hinj r' (by simp [requests]) (by rw [← hname, hreq])
        subst hr
        show r' ∉ (run H app (apply H app o (.req r' b)) (rest ++ more)).log.map (·.request)
        simp only [apply, hsame]
        rw [(stopped_run (H := H) (app := app) hstop (rest ++ more)).2]
        exact hnot
      · exact ih (inv_step hinv r' b) hp' (fun q hq => hinj q (by simp [requests, hq]))

end NCP2
