/-
Each claim of `Statements.lean`, proved from the library, with the axioms it uses.

The gate requires the printed axioms to be `propext`, `Classical.choice`, and `Quot.sound` only.
-/
import NCP2
import Statements

namespace NCP2.Audit

open NCP2 NCP2.Statements

theorem history_chain (H : Frame → Id) (app : App) (inputs : List (Request × AppResult)) :
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

theorem retransmissionIdentical : RetransmissionIdentical := fun _ _ inputs _ a hk =>
  step_retransmit (inv_run inputs) hk a

theorem commitment : Commitment := by
  intro H app in₁ in₂ x₁ x₂ h₁ h₂ hinj hid
  rcases history_chain H app in₁ with e₁ | ⟨y₁, hc₁⟩
  · simp [e₁] at h₁
  rcases history_chain H app in₂ with e₂ | ⟨y₂, hc₂⟩
  · simp [e₂] at h₂
  rw [hc₁.getLast] at h₁; cases h₁
  rw [hc₂.getLast] at h₂; cases h₂
  exact hc₁.unique hc₂ hinj hid

theorem responsesOf_eq (H : Frame → Id) (app : App) :
    ∀ (o : Owner) (inputs : List (Request × AppResult)),
      OkIsOwnExecution.responsesOf H app o inputs = responses H app o inputs
  | _, [] => rfl
  | o, (r, a) :: rest => by
    simp [OkIsOwnExecution.responsesOf, responses, responsesOf_eq H app _ rest]

theorem okIsOwnExecution : OkIsOwnExecution := by
  intro H app inputs r p hp hok hreq hinj
  rw [responsesOf_eq] at hp
  exact ok_is_own_execution inv_init inputs hp hok hreq hinj

theorem rejectionMeansNeverExecuted : RejectionMeansNeverExecuted :=
  fun _ _ inputs r a hrej hcode => step_rejected_not_logged (inv_run inputs) r a hrej hcode

theorem staleMayHaveExecuted : StaleMayHaveExecuted :=
  ⟨_, _, _, _, _, seqStale_after_execution⟩

end NCP2.Audit

#print axioms NCP2.Audit.atMostOnce
#print axioms NCP2.Audit.inOrder
#print axioms NCP2.Audit.acknowledged
#print axioms NCP2.Audit.nothingAfterEnd
#print axioms NCP2.Audit.rejectedChangesNothing
#print axioms NCP2.Audit.retransmissionIdentical
#print axioms NCP2.Audit.commitment
#print axioms NCP2.Audit.okIsOwnExecution
#print axioms NCP2.Audit.rejectionMeansNeverExecuted
#print axioms NCP2.Audit.staleMayHaveExecuted
