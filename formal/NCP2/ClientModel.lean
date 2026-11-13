/-
A client that follows section 7.6, as a Lean model (spec 7.6 and 7.7, property 7).

The client takes three kinds of events: it sends its next request, a response arrives, or its time
limit passes after the last copy. Responses arrive from the network in any order, also copies and
responses to other requests; the client accepts only the one that names its outstanding request
(rule 7.6.2, as on the Zenoh binding). The model records each verdict, with the response that gave
it, as ghost state. This file holds only definitions; `ClientProofs.lean` proves what the verdicts
mean.
-/
import NCP2.Model

namespace NCP2

/-- What a client concludes about one of its requests. -/
inductive Verdict where
  /-- The request executed once: `ok`, or `ended` with `result_too_large`. -/
  | ran
  /-- The request never executes: `declined`, or `ended` with `shutdown`. -/
  | notRun
  /-- The owner did not admit this frame. -/
  | rejected
  /-- The request is possibly executed. -/
  | unknown
  deriving DecidableEq, Repr

/-- The verdict of a response that names the client's request (rules 7.6.3 to 7.6.5). -/
def verdictOf (p : Response) : Verdict :=
  match p.outcome, p.code with
  | .ok, _ => .ran
  | .declined, _ => .notRun
  | .rejected, _ => .rejected
  | .ended, some .resultTooLarge => .ran
  | .ended, some .shutdown => .notRun
  | .ended, _ => .unknown

/-- One verdict: the request, the verdict, and the response that gave it, if any. -/
abbrev Record := Request × Verdict × Option Response

/-- The client state of section 7.6, with the verdicts as ghost state. -/
structure Client where
  session : Nat
  seq : Nat := 0
  ack : Option Id := none
  pending : Option Request := none
  opened : Bool := false
  ended : Bool := false
  verdicts : List Record := []

inductive ClientEvent where
  /-- The client makes its next request: an `open` first, then calls and `close`. -/
  | send (op : Op) (body : Nat)
  /-- A response arrives. -/
  | receive (p : Response)
  /-- The time limit passes after the last copy of the outstanding request (rule 7.6.7). -/
  | timeout

section Client

variable (H : Frame → Id)

/-- Rules 7.6.1 to 7.6.7 for one event. -/
def clientStep (c : Client) : ClientEvent → Client
  | .send op body =>
    if c.ended ∨ c.pending.isSome then c
    else if op = .openSession then
      if c.opened then c
      else { c with pending := some { protocol := 2, session := c.session, seq := 0, op,
                                      ack := none, body } }
    else if c.opened then
      { c with pending := some { protocol := 2, session := c.session, seq := c.seq + 1, op,
                                 ack := c.ack, body } }
    else c
  | .receive p =>
    match c.pending with
    | none => c
    | some r =>
      if p.session = r.session ∧ p.seq = r.seq ∧ p.request = H (.req r) then
        match p.outcome with
        | .ok => { c with pending := none, seq := r.seq, ack := some (H (.resp p)), opened := true,
                          ended := decide (r.op = .close),
                          verdicts := c.verdicts ++ [(r, .ran, some p)] }
        | .declined => { c with pending := none, seq := r.seq, ack := some (H (.resp p)),
                                verdicts := c.verdicts ++ [(r, .notRun, some p)] }
        | .rejected =>
          -- Rule 7.6.4: a rejection of a request other than `open` ends the session, possibly
          -- executed: the owner lost the session, and a delayed copy of `open` opened it again.
          if r.op = .openSession then
            { c with pending := none, verdicts := c.verdicts ++ [(r, .rejected, some p)] }
          else
            { c with pending := none, ended := true, verdicts := c.verdicts ++ [(r, .unknown, some p)] }
        | .ended => { c with pending := none, ended := true,
                             verdicts := c.verdicts ++ [(r, verdictOf p, some p)] }
      else c
  | .timeout =>
    match c.pending with
    | none => c
    | some r => { c with pending := none, ended := true, verdicts := c.verdicts ++ [(r, .unknown, none)] }

/-- The client after a sequence of events. -/
def clientRun (c : Client) : List ClientEvent → Client
  | [] => c
  | e :: rest => clientRun (clientStep H c e) rest

end Client

/-- The responses that arrive during a sequence of events. -/
def received : List ClientEvent → List Response
  | [] => []
  | .receive p :: rest => p :: received rest
  | _ :: rest => received rest

end NCP2
