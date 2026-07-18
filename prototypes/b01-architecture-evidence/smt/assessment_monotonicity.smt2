(set-logic QF_UF)

(declare-const local_before Bool)
(declare-const local_after Bool)
(declare-const deny_before Bool)
(declare-const deny_after Bool)
(declare-const authenticated_widen Bool)
(declare-const effective_before Bool)
(declare-const effective_after Bool)
(declare-const widened Bool)
(declare-const deny_applied Bool)
(declare-const disposition_authenticated Bool)
(declare-const disposition_outcome_applied Bool)

(assert (= effective_before (and local_before (not deny_before))))
(assert (= effective_after (and local_after (not deny_after))))
(assert (= widened (and (not effective_before) effective_after)))
(assert
  (=>
    (not authenticated_widen)
    (and (= local_after local_before) (=> deny_before deny_after))))
(assert (=> widened authenticated_widen))
(assert
  (=>
    deny_applied
    (and disposition_authenticated disposition_outcome_applied)))

; EXPECT: sat authenticated_deny_removal_witness
(push)
(assert local_before)
(assert deny_before)
(assert local_after)
(assert (not deny_after))
(assert authenticated_widen)
(assert widened)
(check-sat)
(pop)

; EXPECT: sat authenticated_applied_disposition_witness
(push)
(assert deny_applied)
(assert disposition_authenticated)
(assert disposition_outcome_applied)
(check-sat)
(pop)

; EXPECT: unsat applied_deny_without_authenticated_applied_disposition
(push)
(assert deny_applied)
(assert (not (and disposition_authenticated disposition_outcome_applied)))
(check-sat)
(pop)

; EXPECT: sat assessor_tightening_witness
(push)
(assert local_before)
(assert (not deny_before))
(assert local_after)
(assert deny_after)
(assert (not authenticated_widen))
(assert (not widened))
(check-sat)
(pop)

; EXPECT: unsat unauthenticated_widening
(push)
(assert local_before)
(assert deny_before)
(assert local_after)
(assert (not deny_after))
(assert (not authenticated_widen))
(assert widened)
(check-sat)
(pop)
