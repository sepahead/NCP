/-
Each claim of `Statements.lean`, proved from the library, with the axioms it uses.

The gate requires the printed axioms to be `propext`, `Classical.choice`, and `Quot.sound` only.
-/
import NCP2
import Statements

namespace NCP2.Audit

open NCP2 NCP2.Statements

theorem history_chain (H : Frame → Id) (app : App) (inputs : List Input) :
    history H app inputs = [] ∨ ∃ y, Chain H (history H app inputs) y :=
  run_chain inputs

theorem atMostOnce : AtMostOnce := fun _ _ inputs => run_at_most_once inputs

theorem inOrder : InOrder := by
  intro H app inputs
  rcases history_chain H app inputs with h | ⟨y, hc⟩
  · simp [h]
  · exact hc.seqs

theorem acknowledged : Acknowledged := by
  intro H app inputs i h
  rcases history_chain H app inputs with h' | ⟨y, hc⟩
  · simp [h'] at h
  · exact hc.ack_index i h

theorem nothingAfterEnd : NothingAfterEnd := by
  intro H app inputs i h
  rcases history_chain H app inputs with h' | ⟨y, hc⟩
  · simp [h'] at h
  · exact hc.live_index i h

theorem rejectedChangesNothing : RejectedChangesNothing := fun _ _ _ _ _ h => step_rejected h

theorem retransmissionIdentical : RetransmissionIdentical := fun _ _ inputs _ b hk =>
  step_retransmit (inv_run inputs) hk b

theorem framesOf_eq (xs : List Exchange) : framesOf xs = frames xs := rfl

theorem commitment : Commitment := by
  intro H app in₁ in₂ x₁ x₂ h₁ h₂ hinj hid
  rcases history_chain H app in₁ with e₁ | ⟨y₁, hc₁⟩
  · simp [e₁] at h₁
  rcases history_chain H app in₂ with e₂ | ⟨y₂, hc₂⟩
  · simp [e₂] at h₂
  rw [hc₁.getLast] at h₁; cases h₁
  rw [hc₂.getLast] at h₂; cases h₂
  exact hc₁.unique hc₂ hinj hid

/-- Two histories whose first responses have different bodies share no request after `open`. -/
theorem openings_disjoint_of_bodies (H : Frame → Id) (app : App) (in₁ in₂ : List Input)
    (x₁ x₂ : Exchange) (h₁ : (history H app in₁).head? = some x₁)
    (h₂ : (history H app in₂).head? = some x₂) (hbody : x₁.response.body ≠ x₂.response.body)
    (hinj : ∀ f ∈ framesOf (history H app in₁), ∀ g ∈ framesOf (history H app in₂),
      H f = H g → f = g) :
    ∀ r ∈ (history H app in₁).map (·.request), r ∈ (history H app in₂).map (·.request) →
      r.seq = 0 := by
  intro r hr₁ hr₂
  rcases history_chain H app in₁ with e₁ | ⟨y₁, hc₁⟩
  · simp [e₁] at h₁
  rcases history_chain H app in₂ with e₂ | ⟨y₂, hc₂⟩
  · simp [e₂] at h₂
  obtain ⟨a, ha, rfl⟩ := List.mem_map.1 hr₁
  obtain ⟨b, hb, hab⟩ := List.mem_map.1 hr₂
  obtain ⟨i, hi, rfl⟩ := List.getElem_of_mem ha
  obtain ⟨j, hj, rfl⟩ := List.getElem_of_mem hb
  have hsi := hc₁.seq_index i hi
  have hsj := hc₂.seq_index j hj
  have hij : i = j := by rw [← hsi, ← hsj, hab]
  subst hij
  rw [hsi]
  rcases Nat.eq_zero_or_pos i with h0 | hpos
  · exact h0
  · exfalso
    obtain ⟨k, rfl⟩ : ∃ k, i = k + 1 := ⟨i - 1, by omega⟩
    have hroot := hc₁.shared_prefix hc₂ hinj k hi hj hab.symm
    have hx₁ : x₁ = (history H app in₁)[0]'(by omega) := by
      rw [List.head?_eq_getElem?, List.getElem?_eq_getElem (by omega)] at h₁
      exact (Option.some.inj h₁).symm
    have hx₂ : x₂ = (history H app in₂)[0]'(by omega) := by
      rw [List.head?_eq_getElem?, List.getElem?_eq_getElem (by omega)] at h₂
      exact (Option.some.inj h₂).symm
    exact hbody (by rw [hx₁, hx₂, hroot])

theorem history_some_head {H : Frame → Id} {app : App} {inputs : List Input} {r : Request}
    (hr : r ∈ (history H app inputs).map (·.request)) :
    ∃ x, (history H app inputs).head? = some x := by
  cases hh : history H app inputs with
  | nil => rw [hh] at hr; simp at hr
  | cons a l => exact ⟨a, rfl⟩

theorem openingsDisjoint : OpeningsDisjoint := by
  intro H app in₁ in₂ hnonce hinj r hr₁ hr₂
  obtain ⟨x₁, h₁⟩ := history_some_head hr₁
  obtain ⟨x₂, h₂⟩ := history_some_head hr₂
  obtain ⟨q₁, b₁, bd₁, hm₁, hop₁, -, hb₁⟩ := history_head (H := H) (app := app) in₁ x₁ h₁
  obtain ⟨q₂, b₂, bd₂, hm₂, hop₂, -, hb₂⟩ := history_head (H := H) (app := app) in₂ x₂ h₂
  have hbody : x₁.response.body ≠ x₂.response.body := by
    rw [hb₁, hb₂]
    intro h
    injection h with _ hn
    exact hnonce q₁ b₁ q₂ b₂ hm₁ hm₂ hop₁ hop₂ hn
  exact openings_disjoint_of_bodies H app in₁ in₂ x₁ x₂ h₁ h₂ hbody hinj r hr₁ hr₂

theorem historyFromInputs : HistoryFromInputs := by
  intro H app inputs x hx
  rcases run_log_sub (H := H) (app := app) (o := {}) inputs x hx with h | h
  · simp at h
  · exact h

theorem okIsOwnExecution : OkIsOwnExecution := by
  intro H app inputs r p hp hok hreq hinj
  refine ok_is_own_execution inv_init inputs hp hok hreq fun q hq hqr => hinj q ?_ hqr
  obtain ⟨x, hx, rfl⟩ := List.mem_map.1 hq
  exact historyFromInputs H app inputs x hx

theorem declinedIsFinal : DeclinedIsFinal := by
  intro H app inputs more r p hp hd hreq hinj
  refine declined_is_final inv_init inputs more hp hd hreq fun q hq hqr => hinj q ?_ hqr
  obtain ⟨x, hx, rfl⟩ := List.mem_map.1 hq
  exact historyFromInputs H app (inputs ++ more) x hx

theorem shutdownIsFinal : ShutdownIsFinal := fun _ _ inputs more _ _ hp hs hreq hinj =>
  shutdown_is_final inv_init inputs more hp hs hreq hinj

theorem rejectionMeansNotAdmitted : RejectionMeansNotAdmitted :=
  fun _ _ inputs r b hrej hcode => step_rejected_not_logged (inv_run inputs) r b hrej hcode

theorem staleMayHaveExecuted : StaleMayHaveExecuted :=
  fun H => ⟨_, _, _, _, seqStale_after_execution H⟩

theorem nothingAfterStop : NothingAfterStop := by
  intro H app inputs more
  unfold history
  rw [run_append]
  exact (stopped_run (H := H) (app := app) (o := { run H app {} inputs with stopped := true }) rfl more).2

theorem honestCalls_log (H : Frame → Id) (app : App) (s : Nat) :
    ∀ (calls : List (Nat × Nat × Behavior)) (o : Owner) (seq : Nat) (p : Response) (k : Exchange),
      o.session = some s → o.kept = some k → k.response = p → o.high + 1 = seq →
      o.ended = false → o.stopped = false →
      (∀ c ∈ calls, app.known c.1 = true ∧ c.2.2.valid = true ∧ ∃ v, c.2.2.result = .result v) →
      (honestCalls H app s o seq p calls).log.map (fun x => (x.request.op, x.request.body)) =
        o.log.map (fun x => (x.request.op, x.request.body)) ++
          calls.map (fun c => (Op.call c.1, c.2.1))
  | [], _, _, _, _, _, _, _, _, _, _, _ => by simp [honestCalls]
  | (name, body, b) :: rest, o, seq, p, k, hs, hk, hp, hh, hend, hstop, hcalls => by
    obtain ⟨hknown, hvalid, v, hres⟩ := hcalls (name, body, b) (by simp)
    subst hp
    have hstep := step_call (H := H) (app := app)
      (r := { protocol := 2, session := s, seq, op := .call name,
              ack := some (H (.resp k.response)), body })
      (b := b) hs hk hend hstop rfl rfl hh.symm rfl rfl hknown hvalid hres
    have ih := honestCalls_log H app s rest
      { o with
        high := seq,
        kept := some ⟨{ protocol := 2, session := s, seq, op := .call name,
                        ack := some (H (.resp k.response)), body },
                      reply H { protocol := 2, session := s, seq, op := .call name,
                                ack := some (H (.resp k.response)), body } .ok none (.result v)⟩,
        ended := false,
        log := o.log ++ [⟨{ protocol := 2, session := s, seq, op := .call name,
                            ack := some (H (.resp k.response)), body },
                          reply H { protocol := 2, session := s, seq, op := .call name,
                                    ack := some (H (.resp k.response)), body } .ok none
                            (.result v)⟩] }
      (seq + 1)
      (reply H { protocol := 2, session := s, seq, op := .call name,
                 ack := some (H (.resp k.response)), body } .ok none (.result v))
      _ hs rfl rfl (by simp) rfl hstop (fun c hc => hcalls c (by simp [hc]))
    simp only [honestCalls, hstep]
    rw [ih]
    simp

theorem faultFreeProgress : FaultFreeProgress := by
  intro H app s body bound b0 calls hopen hcalls r0
  have h0 := step_open (H := H) (app := app) (r := r0) (b := b0) rfl rfl rfl rfl hopen
  have ih := honestCalls_log H app s calls
    { session := some r0.session, bound, high := 0,
      kept := some ⟨r0, reply H r0 .ok none (.opened bound b0.nonce)⟩, ended := false,
      log := [⟨r0, reply H r0 .ok none (.opened bound b0.nonce)⟩] }
    1 (reply H r0 .ok none (.opened bound b0.nonce)) _ rfl rfl rfl rfl rfl rfl hcalls
  rw [h0, ih]
  simp [r0]

theorem unknownIsLast : UnknownIsLast := fun _ s events i h => unknown_is_last s events i h

theorem rejectedOnlyForOpen : RejectedOnlyForOpen := fun _ s events => rejected_only_open s events

theorem clientTruthful : ClientTruthful := fun _ app s events inputs more hrecv hinj =>
  client_truthful app s events inputs more hrecv hinj

end NCP2.Audit

#print axioms NCP2.Audit.atMostOnce
#print axioms NCP2.Audit.inOrder
#print axioms NCP2.Audit.acknowledged
#print axioms NCP2.Audit.nothingAfterEnd
#print axioms NCP2.Audit.rejectedChangesNothing
#print axioms NCP2.Audit.retransmissionIdentical
#print axioms NCP2.Audit.commitment
#print axioms NCP2.Audit.openingsDisjoint
#print axioms NCP2.Audit.okIsOwnExecution
#print axioms NCP2.Audit.declinedIsFinal
#print axioms NCP2.Audit.shutdownIsFinal
#print axioms NCP2.Audit.rejectionMeansNotAdmitted
#print axioms NCP2.Audit.staleMayHaveExecuted
#print axioms NCP2.Audit.nothingAfterStop
#print axioms NCP2.Audit.historyFromInputs
#print axioms NCP2.Audit.faultFreeProgress
#print axioms NCP2.Audit.unknownIsLast
#print axioms NCP2.Audit.rejectedOnlyForOpen
#print axioms NCP2.Audit.clientTruthful
