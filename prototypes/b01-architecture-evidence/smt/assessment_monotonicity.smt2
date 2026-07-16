(set-logic QF_UF)

(declare-const local_before Bool)
(declare-const local_after Bool)
(declare-const deny_before Bool)
(declare-const deny_after Bool)
(declare-const authenticated_widen Bool)
(declare-const effective_before Bool)
(declare-const effective_after Bool)
(declare-const widened Bool)

(assert (= effective_before (and local_before (not deny_before))))
(assert (= effective_after (and local_after (not deny_after))))
(assert (= widened (and (not effective_before) effective_after)))
(assert
  (=>
    (not authenticated_widen)
    (and (= local_after local_before) (=> deny_before deny_after))))
(assert (=> widened authenticated_widen))

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
