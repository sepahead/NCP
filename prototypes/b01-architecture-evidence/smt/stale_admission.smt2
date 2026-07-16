(set-logic QF_LIA)

(declare-const current_term Int)
(declare-const command_term Int)
(declare-const current_generation Int)
(declare-const command_generation Int)
(declare-const current_epoch Int)
(declare-const command_epoch Int)
(declare-const holder_matches Bool)
(declare-const lease_live Bool)
(declare-const active Bool)
(declare-const plant_domain Bool)
(declare-const admitted Bool)

(assert
  (=
    admitted
    (and
      (= command_term current_term)
      (= command_generation current_generation)
      (= command_epoch current_epoch)
      holder_matches
      lease_live
      active
      plant_domain)))

; EXPECT: sat exact_current_fence_witness
(push)
(assert (= command_term current_term))
(assert (= command_generation current_generation))
(assert (= command_epoch current_epoch))
(assert holder_matches)
(assert lease_live)
(assert active)
(assert plant_domain)
(assert admitted)
(check-sat)
(pop)

; EXPECT: unsat stale_generation_admission
(push)
(assert (= command_term current_term))
(assert (not (= command_generation current_generation)))
(assert (= command_epoch current_epoch))
(assert holder_matches)
(assert lease_live)
(assert active)
(assert plant_domain)
(assert admitted)
(check-sat)
(pop)
