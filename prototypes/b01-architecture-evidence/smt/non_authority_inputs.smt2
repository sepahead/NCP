(set-logic QF_UF)

(declare-const body_lease Bool)
(declare-const plant_session Bool)
(declare-const current_commander Bool)
(declare-const core_route Bool)
(declare-const observer_grant Bool)
(declare-const pid_result Bool)
(declare-const cortex_export Bool)
(declare-const simulation_grant Bool)
(declare-const plant_admit Bool)

(assert
  (=
    plant_admit
    (and body_lease plant_session current_commander core_route)))

; EXPECT: sat valid_body_authority_witness
(push)
(assert body_lease)
(assert plant_session)
(assert current_commander)
(assert core_route)
(assert plant_admit)
(check-sat)
(pop)

; EXPECT: unsat observer_pid_export_or_simulation_grant_cannot_replace_body_lease
(push)
(assert (not body_lease))
(assert plant_session)
(assert current_commander)
(assert core_route)
(assert observer_grant)
(assert pid_result)
(assert cortex_export)
(assert simulation_grant)
(assert plant_admit)
(check-sat)
(pop)
