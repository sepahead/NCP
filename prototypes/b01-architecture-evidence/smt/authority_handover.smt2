(set-logic QF_UF)

(declare-const old_revoked Bool)
(declare-const old_admission_open Bool)
(declare-const quiesced Bool)
(declare-const higher_term Bool)
(declare-const grant_new Bool)
(declare-const old_live Bool)
(declare-const new_live Bool)

(assert (= old_live (not old_revoked)))
(assert (= new_live grant_new))
(assert
  (=>
    grant_new
    (and old_revoked (not old_admission_open) quiesced higher_term)))

; EXPECT: sat grant_after_complete_cut_witness
(push)
(assert grant_new)
(check-sat)
(pop)

; EXPECT: unsat old_and_new_live_overlap
(push)
(assert old_live)
(assert new_live)
(check-sat)
(pop)
