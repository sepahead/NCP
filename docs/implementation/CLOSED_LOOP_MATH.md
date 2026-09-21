# Closed-loop identity, timing, and stability

This note recovers mathematical distinctions from the earlier candidate design work.
It is informative. It allocates no wire field and supplies no qualification result.
The [selected architecture](NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md) owns the broader candidate design.
The [modular application guide](../../local/modular/STATUS.md) owns current application scope and evidence.

## A complete feedback cycle

Let $k$ be a nonnegative integer sample index.
Let $x_k$ be plant state, $w_k$ a sensor disturbance, and $h$ the installed sampling function.
The observation is $y_k=h(x_k,w_k)$.
The deployment defines state coordinates, disturbance assumptions, sensor units, and the function $h$.
NCP does not infer these properties from message delivery.

A controller uses the observation to propose an action.
The body admits or rejects that proposal under its selected contract.
The deployment applies an input and produces the next state.
A causally later observation completes the feedback cycle.
One sensor-to-command exchange does not establish that complete cycle.

The selected software action and actual plant input are different quantities.
A disposition records the software outcome that its contract defines.
It does not, by itself, measure actuator motion or establish a physical effect.
An absent action is not numeric zero. A deployment must define its restrictive action explicitly.

## Exact source identity

For the broader candidate's prepared design, write the full source coordinate as

$$
\Sigma_k=(\Lambda_k,q_k,c_k).
$$

Here, $\Lambda_k$ is the prepared source declaration, $q_k$ its stream position, and $c_k$ the retained publication digest.
The declaration binds the realm, session generation, route, publisher, frame class, layout, security activation, and source epoch.
A compact wire projection does not repeat every member of this coordinate.
The receiver must resolve the projection through its prepared declaration and retained source record.

Arrival order, a nearby timestamp, or the latest sensor value cannot replace that exact join.
The join establishes the declared source identity.
It cannot prove that opaque controller code used the declared sample to compute its proposal.
Application correctness and protocol correlation require separate evidence.

## Causal time intervals

Let $\tau_k$ be sample time on one body-owned monotonic clock incarnation.
Use seconds for every duration in this note.
The realized interval is

$$
\Delta_k=\tau_{k+1}-\tau_k>0.
$$

The controller cannot know this future realized interval when it chooses action $k$.
A controller that uses the previous measured interval instead receives

$$
\delta_k=
\begin{cases}
\Delta_{\mathrm{init}}, & k=0,\\
\tau_k-\tau_{k-1}, & k\geq1.
\end{cases}
$$

The positive initial value $\Delta_{\mathrm{init}}$ belongs to the controller profile.
Other controllers can use a declared nominal period.
A missing interval or clock-incarnation change requires the selected fault policy. It cannot justify an invented measurement.

Let $t_s$, $t_a$, and $t_d$ denote sample retention, action admission, and terminal disposition on that same clock.
When those events exist, their intervals are

$$
L_a=t_a-t_s,\qquad L_d=t_d-t_s.
$$

For an admitted action whose terminal disposition follows admission, $0\leq L_a\leq L_d$.
Neither interval measures physical response.
A rejected action need not have an admission event, so $L_a$ can be undefined.
Never substitute zero for an absent event.

An exclusive deadline $d$ accepts only $t_a<d$.
For example, admission at $0.012$ seconds satisfies deadline $0.015$ seconds.
Admission at exactly $0.015$ seconds is expired.
Subtracting unrelated publisher and receiver clocks does not produce an equivalent measurement.

## Stability needs a plant and controller model

Consider a continuous linear plant with constant matrices:

$$
\dot x(t)=A_cx(t)+B_cu(t).
$$

Here, $x(t)\in\mathbb{R}^n$ is state and $u(t)\in\mathbb{R}^m$ is input.
The matrix dimensions are $A_c\in\mathbb{R}^{n\times n}$ and $B_c\in\mathbb{R}^{n\times m}$.
Their units must map the selected state and input units to state change per second.

Assume exact state measurement, no disturbance, no saturation, no delay, and an input held constant between samples.
For a positive sample period $\Delta$, integration gives

$$
A_d(\Delta)=e^{A_c\Delta},\qquad
B_d(\Delta)=\int_0^\Delta e^{A_c\theta}B_c\,d\theta.
$$

With state feedback $u_k=Kx_k$, define $M(\Delta)=A_d(\Delta)+B_d(\Delta)K$.
The gain matrix $K\in\mathbb{R}^{m\times n}$ maps state units to input units.
The sampled system satisfies $x_{k+1}=M(\Delta)x_k$.
For a fixed period, asymptotic stability is equivalent to $\rho(M(\Delta))<1$.
The spectral radius $\rho$ is the largest absolute eigenvalue.

For a scalar position integrator, let $\dot x=u$ and $u_k=-2x_k$.
Position uses meters, input uses meters per second, and the gain is $-2\,\mathrm{s}^{-1}$.
Then $M(\Delta)=1-2\Delta$.
At $\Delta=0.1$ seconds, $M=0.8$, so each ideal step retains 80 percent of the previous position error.
At $\Delta=1$ second, $M=-1$: the error alternates without decay.
Successful message exchange would not distinguish these stability outcomes.

## Variable periods need a stronger argument

Checking each spectral radius separately does not generally prove stability under arbitrary switching between matrix transitions.
Let $\mathcal{D}$ be the nonempty admitted period set.
One sufficient condition is a common pair of symmetric positive-definite matrices $P,Q\in\mathbb{R}^{n\times n}$ such that

$$
M(\delta)^\mathsf{T}P M(\delta)-P\preceq-Q
\quad\text{for every }\delta\in\mathcal{D}.
$$

The matrix inequality means that every state vector gives a nonpositive quadratic form after moving the right side left.
For $V(x)=x^\mathsf{T}Px$, substitution gives

$$
V(x_{k+1})-V(x_k)\leq-x_k^\mathsf{T}Qx_k.
$$

Define $\alpha=\lambda_{\min}(Q)/\lambda_{\max}(P)>0$.
The inequalities imply $V(x_{k+1})\leq(1-\alpha)V(x_k)$, establishing uniform decay for the admitted transitions.
The certificate can be conservative. Failure to find it does not prove instability.

These algebraic implications are conditional deductions, not a machine-checked controller certificate.
No $P,Q$ pair is supplied for an ecosystem controller here.
A deployment must separately cover its delays, jitter, saturation, estimation, quantization, loss, restrictive transitions, and nonlinearities.
NCP acceptance does not establish those assumptions or controller stability.
