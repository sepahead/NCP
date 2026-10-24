/-
The verified owner model as a test oracle (see README.md).

The conformance harness `../model/conformance.py --oracle` sends one request per line and compares
the real owners' outcomes and codes with the ones printed here. The step function is
`NCP2.step`, the function that `NCP2.Owner` proves safe.

Input, one request per line:  SEQ OP ACK BAD FAIL
  OP    open | close | step | unknown
  ACK   - | an identity printed earlier by this oracle
  BAD   1 if the application must find the body invalid, else 0
  FAIL  1 if the application must raise when it executes the request, else 0
Output, one line per request: OUTCOME CODE IDENTITY  (CODE and IDENTITY are - when absent)

The session and protocol are those of the harness's one session. Identities are hashes of the
abstract frames; the oracle stops with an error if two different frames ever share one, so every
run it completes is a run of the model under an injective digest.
-/
import NCP2

open NCP2

def codeName : Code → String
  | .wrongProtocol => "wrong_protocol" | .notOpen => "not_open" | .alreadyOpen => "already_open"
  | .wrongSession => "wrong_session" | .seqStale => "seq_stale" | .seqGap => "seq_gap"
  | .seqConflict => "seq_conflict" | .ackMissing => "ack_missing" | .ackMismatch => "ack_mismatch"
  | .unknownOp => "unknown_op" | .bodyInvalid => "body_invalid"
  | .contractMismatch => "contract_mismatch" | .boundUnacceptable => "bound_unacceptable"
  | .sessionEnded => "session_ended" | .resultTooLarge => "result_too_large"
  | .ownerFailure => "owner_failure"

def outcomeName : Outcome → String
  | .ok => "ok" | .rejected => "rejected" | .ended => "ended"

def digest (f : Frame) : Id := (hash f).toNat

/-- The harness's application: one operation, `step` (name 0). Body bit 1: invalid; bit 0: raise. -/
def harnessApp : App where
  known name := name == 0
  valid _ body := body / 2 % 2 == 0
  opening _ := .accept 65536

def parseLine (line : String) : Option (Request × AppResult) := do
  let parts := (line.splitOn " ").filter (· ≠ "")
  let [seqS, opS, ackS, badS, failS] := parts | none
  let seq ← seqS.toNat?
  let op ← match opS with
    | "open" => some Op.openSession | "close" => some Op.close
    | "step" => some (Op.call 0) | "unknown" => some (Op.call 1) | _ => none
  let ack ← if ackS == "-" then some none else (some ∘ some) <$> ackS.toNat? |>.join
  let bad := badS == "1"
  let fail := failS == "1"
  let body := (if bad then 2 else 0) + (if fail then 1 else 0)
  let request : Request := { protocol := 2, session := 1, seq, op, ack, body }
  some (request, if fail then .error else .result seq)

partial def loop (stdin : IO.FS.Stream) (stdout : IO.FS.Stream) (o : Owner)
    (seen : List (Id × Frame)) : IO Unit := do
  let line ← stdin.getLine
  if line.isEmpty then return
  let line := line.trimAsciiEnd.toString
  if line.isEmpty then loop stdin stdout o seen else
  let some (r, a) := parseLine line
    | throw (IO.userError s!"cannot parse: {line}")
  let (o', p) := step digest harnessApp o r a
  -- Check that the digest is injective on every frame seen so far.
  let mut seen := seen
  for f in [Frame.req r, Frame.resp p] do
    match seen.find? (·.1 == digest f) with
    | some (_, g) => if g != f then throw (IO.userError "digest collision")
    | none => seen := (digest f, f) :: seen
  let ident := if p.outcome == .rejected then "-" else toString (digest (.resp p))
  let code := match p.code with | some c => codeName c | none => "-"
  stdout.putStrLn s!"{outcomeName p.outcome} {code} {ident}"
  stdout.flush
  loop stdin stdout o' seen

def main : IO Unit := do
  loop (← IO.getStdin) (← IO.getStdout) {} []
