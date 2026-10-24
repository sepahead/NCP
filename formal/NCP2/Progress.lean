/-
Progress without faults. The safety theorems would also hold for an owner that executes nothing;
these lemmas show that the model executes what a correct client sends over a network that delivers
each frame once and in order. `Statements.FaultFreeProgress` states the result for a whole session.
-/
import NCP2.Owner

namespace NCP2

variable {H : Frame → Id} {app : App}

/-- An `open` request whose body the application accepts opens the session. -/
theorem step_open {r : Request} {b : Behavior} {bound : Nat}
    (hprot : r.protocol = 2) (hop : r.op = .openSession) (hseq : r.seq = 0) (h_ack : r.ack = none)
    (hopen : app.opening r.body = .accept bound) :
    step H app {} r b =
      ({ session := some r.session, bound, high := 0,
         kept := some ⟨r, reply H r .ok none (.opened bound)⟩, ended := false,
         log := [⟨r, reply H r .ok none (.opened bound)⟩] },
       reply H r .ok none (.opened bound)) := by
  simp [step, openStep, hprot, hop, hseq, h_ack, hopen]

/-- A call with the next sequence number and the identity of the kept response, for an operation
of the contract whose body the application finds valid and that returns a result, is executed and
kept. -/
theorem step_call {o : Owner} {s name v : Nat} {k : Exchange} {r : Request} {b : Behavior}
    (hs : o.session = some s) (hk : o.kept = some k) (hend : o.ended = false)
    (hprot : r.protocol = 2) (hsess : r.session = s) (hseq : r.seq = o.high + 1)
    (h_ack : r.ack = some (H (.resp k.response))) (hop : r.op = .call name)
    (hknown : app.known name = true) (hvalid : b.valid = true) (hres : b.result = .result v) :
    step H app o r b =
      ({ o with high := r.seq, kept := some ⟨r, reply H r .ok none (.result v)⟩, ended := false,
                log := o.log ++ [⟨r, reply H r .ok none (.result v)⟩] },
       reply H r .ok none (.result v)) := by
  have hnlt : ¬ o.high + 1 < o.high := by omega
  simp [step, checkThenAccept, accept, execute, hs, hk, hend, hprot, hsess, hseq, h_ack, hop,
    hknown, hvalid, hres, hnlt, Ends, reply]

end NCP2
