function [x_best, f_best, info] = QHW(fun, lb, ub, opts)
%QHW  Quantum-inspired Harmonic Wave Optimizer (Q-HW)
%
%  A population-based metaheuristic where each candidate solution is
%  represented as a quantum oscillator (qubit). The phase-update rule
%  is governed by Kuramoto coupled-oscillator synchronization dynamics,
%  replacing the standard rotation-table of canonical QIEA (Han & Kim, 2002)
%  with a physics-derived, population-aware rotation operator.
%
% ── SYNTAX ───────────────────────────────────────────────────────────────────
%  [x_best, f_best, info] = QHW(fun, lb, ub)
%  [x_best, f_best, info] = QHW(fun, lb, ub, opts)
%
% ── INPUTS ───────────────────────────────────────────────────────────────────
%  fun    : objective function handle  @(x) → scalar  (minimization)
%           x is a 1×D row vector
%  lb     : 1×D lower bounds
%  ub     : 1×D upper bounds
%  opts   : (optional) struct — see QHW_defaults() below for all fields
%
% ── OUTPUTS ──────────────────────────────────────────────────────────────────
%  x_best : 1×D optimal solution vector
%  f_best : scalar optimal objective value
%  info   : struct with diagnostic fields:
%             .hist_best   T×1  best fitness per generation
%             .hist_mean   T×1  mean population fitness
%             .hist_r      T×1  Kuramoto order parameter r(t) ∈ [0,1]
%             .hist_sigma  T×1  noise schedule σ(t)
%             .hist_NFE    T×1  cumulative function evaluations
%             .NFE         total function evaluations used
%             .generations number of generations executed
%             .Theta_final N×D  quantum angles at termination
%             .F_final     N×1  population fitness at termination
%
% ── MATHEMATICAL FOUNDATION ──────────────────────────────────────────────────
%
%  (I) QUANTUM REPRESENTATION
%  Each of the N candidates i has a quantum chromosome
%
%      Θ_i = [θ_i¹, …, θ_iᴰ],   θ_iᵏ ∈ [0, π/2]
%
%  interpreted as a qubit rotation angle. The quantum state is:
%
%      |ψ_iᵏ⟩ = cos(θ_iᵏ)|0⟩ + sin(θ_iᵏ)|1⟩
%
%  Measurement (collapse) maps angles to real parameters:
%
%      x_iᵏ = lb_k + (ub_k − lb_k) · sin²(θ_iᵏ)          … (1)
%
%  so P(x_iᵏ near ub_k) = sin²(θ_iᵏ), P(x_iᵏ near lb_k) = cos²(θ_iᵏ).
%
%  (II) FITNESS AS STRIKING FORCE (Boltzmann weights)
%  The quality ("impact force") of oscillator j is:
%
%      F̃_j = (F_j − Fmin)/(Fmax − Fmin)          (normalized, ∈ [0,1])
%
%      w_j = exp(−γ · F̃_j) / Σ_l exp(−γ · F̃_l)  … (2)
%
%  Better solutions (lower F) receive higher weights → stronger coupling
%  influence on the population (tuning-fork analogy: harder strike = louder).
%
%  (III) KURAMOTO ORDER PARAMETER
%  For each dimension k, the synchronization level is measured by:
%
%      r_k(t) = |1/N · Σ_j exp(2i·θ_jᵏ)|  ∈ [0,1]      … (3)
%
%      r(t) = (1/D) · Σ_k r_k(t)   (global order parameter)
%
%  r → 1 : full synchronization  → population has converged
%  r → 0 : incoherence           → population is exploring
%  r(t) serves as a rigorously measurable convergence indicator.
%
%  (IV) ADAPTIVE COUPLING STRENGTH
%  The global coupling K_t adapts via the order parameter:
%
%      K_t = K_min + (K_max − K_min)·(1 − r(t))          … (4)
%
%  When disordered (r≈0): high K drives synchronization (exploitation push).
%  When synchronized (r≈1): low K prevents premature convergence.
%
%  (V) PHASE UPDATE — QUANTUM-KURAMOTO ROTATION OPERATOR
%  For each candidate i and dimension k:
%
%  Δθ_iᵏ = K_t · η · [Σ_{j≠i} w_j · sin(θ_jᵏ − θ_iᵏ)]    ← Kuramoto
%         +        η_g · sin(θ*ᵏ − θ_iᵏ)                   ← global attractor
%         +        σ_t · ε_iᵏ ,   ε_iᵏ ~ N(0,1)            ← quantum noise
%                                                             … (5)
%
%  θ_iᵏ(t+1) = reflect( θ_iᵏ(t) + Δθ_iᵏ , [0, π/2] )       … (6)
%
%  The Kuramoto term is evaluated efficiently using the identity
%  sin(a−b) = sin(a)cos(b) − cos(a)sin(b):
%
%  Σ_j w_j·sin(θ_j−θ_i) = [Σ_j w_j·sin(θ_j)]·cos(θ_i) − [Σ_j w_j·cos(θ_j)]·sin(θ_i)
%
%  The j=i self-term vanishes (sin(0)=0), so no correction is needed.
%  Computational complexity per generation: O(N·D), not O(N²·D).
%
%  CONSTRUCTIVE INTERFERENCE: when phases θ_j ≈ θ_i, sin(θ_j−θ_i)≈0,
%  reinforcing the region — exploitation.
%  DESTRUCTIVE INTERFERENCE: when phases are antiphase, the sum cancels
%  contributions from weak oscillators — implicit direction pruning.
%
%  (VI) NOISE ANNEALING (quantum decoherence schedule)
%
%      σ_t = max(σ_min, σ₀ · α^t)                           … (7)
%
%  (VII) QUANTUM TUNNELING (escape from local optima)
%  With probability p_tun per generation, the worst q·N individuals
%  are re-initialized with uniform random angles:
%
%      θ_worst ~ U[0, π/2]                                   … (8)
%
%  This mimics quantum tunneling through potential barriers.
%
% ── REFERENCES ───────────────────────────────────────────────────────────────
%  [1] Han, K-H. & Kim, J-H. (2002). Quantum-inspired evolutionary algorithm
%      for a class of combinatorial optimization.
%      IEEE Trans. Evol. Comp., 6(6), 580–593.
%  [2] Kuramoto, Y. (1984). Chemical Oscillations, Waves, and Turbulence.
%      Springer.
%  [3] Strogatz, S.H. (2000). From Kuramoto to Crawford: exploring the onset
%      of synchronization in populations of coupled oscillators.
%      Physica D, 143(1-4), 1–20.
%  [4] Sun, J. et al. (2004). A global search strategy of quantum-behaved
%      particle swarm optimization. CEC 2004.

% ─────────────────────────────────────────────────────────────────────────────
%  DEFAULT OPTIONS
% ─────────────────────────────────────────────────────────────────────────────
def = struct( ...
    'N',          30,    ... % population size
    'T',          300,   ... % max generations
    'eta',        0.30,  ... % Kuramoto learning rate  (η)
    'eta_g',      0.10,  ... % global attractor rate   (η_g)
    'K_min',      0.05,  ... % minimum coupling        (K_min)
    'K_max',      1.00,  ... % maximum coupling        (K_max)
    'gamma',      5.00,  ... % Boltzmann selectivity   (γ)
    'sigma0',     0.10,  ... % initial noise           (σ₀)
    'sigma_min',  0.001, ... % minimum noise           (σ_min)
    'alpha',      0.97,  ... % noise decay rate        (α)
    'p_tun',      0.05,  ... % tunneling probability   (p_tun)
    'q_tun',      0.10,  ... % tunneling fraction      (q_tun)
    'tol',        1e-12, ... % improvement tolerance
    'max_stall',  80,    ... % max stall generations
    'seed',       [],    ... % RNG seed ([] = no seeding)
    'verbose',    true   );  % print progress

if nargin < 4 || isempty(opts)
    opts = def;
else
    fns = fieldnames(def);
    for k = 1:numel(fns)
        if ~isfield(opts, fns{k}), opts.(fns{k}) = def.(fns{k}); end
    end
end

% ─────────────────────────────────────────────────────────────────────────────
%  SETUP
% ─────────────────────────────────────────────────────────────────────────────
if ~isempty(opts.seed), rng(opts.seed); end

lb = lb(:)';  ub = ub(:)';
assert(numel(lb)==numel(ub) && all(ub>lb), 'QHW: invalid bounds.');

D   = numel(lb);
N   = opts.N;
T   = opts.T;
HP  = pi/2;     % half-pi boundary
EPS = 1e-12;

% ─────────────────────────────────────────────────────────────────────────────
%  INITIALIZATION — uniform superposition  θ ~ U[0, π/2]
% ─────────────────────────────────────────────────────────────────────────────
Theta = rand(N, D) * HP;
X     = qhw_decode(Theta, lb, ub);
F     = qhw_eval(fun, X);
NFE   = N;

[f_best, bi]  = min(F);
x_best        = X(bi, :);
theta_best    = Theta(bi, :);

% Pre-allocate history
hist_best  = nan(T, 1);
hist_mean  = nan(T, 1);
hist_r     = nan(T, 1);
hist_sigma = nan(T, 1);
hist_NFE   = nan(T, 1);

sigma_t   = opts.sigma0;
stall_cnt = 0;
T_actual  = T;

if opts.verbose
    fprintf('\n┌─────────────────────────────────────────────────────┐\n');
    fprintf('│       Q-HW  Quantum-inspired Harmonic Wave          │\n');
    fprintf('├─────────────────────────────────────────────────────┤\n');
    fprintf('│  N=%-3d  D=%-3d  T=%-4d  η=%.2f  K=[%.2f,%.2f]       │\n', ...
            N, D, T, opts.eta, opts.K_min, opts.K_max);
    fprintf('├─────────────────────────────────────────────────────┤\n');
    fprintf('  %-6s  %-14s  %-12s  %-7s  %-7s\n', ...
            'Gen','f_best','f_mean','r(t)','σ(t)');
    fprintf('  %s\n', repmat('─', 1, 52));
end

% ─────────────────────────────────────────────────────────────────────────────
%  MAIN LOOP
% ─────────────────────────────────────────────────────────────────────────────
for t = 1:T

    % ── (1) Normalize fitness  F̃_i ∈ [0,1]  (0 = best)
    Fmin = min(F);  Fmax = max(F);
    Fn   = (F - Fmin) / (Fmax - Fmin + EPS);

    % ── (2) Boltzmann fitness weights  w_i ∝ exp(-γ·F̃_i)   [Eq. 2]
    w  = exp(-opts.gamma * Fn);
    w  = w / sum(w);                         % row vector N×1

    % ── (3) Kuramoto order parameter  r(t)                  [Eq. 3]
    r_k = abs(mean(exp(2i * Theta), 1));     % 1×D
    r_t = mean(r_k);

    % ── (4) Adaptive coupling  K_t                          [Eq. 4]
    K_t = opts.K_min + (opts.K_max - opts.K_min) * (1 - r_t);

    % ── (5) Phase update — vectorized O(N·D)                [Eq. 5]
    %     Kuramoto coupling:
    %     Σ_j w_j·sin(θ_j−θ_i) = [w'sin(Θ)]·cos(Θ_i) − [w'cos(Θ)]·sin(Θ_i)
    wS = sum(w .* sin(Theta), 1);            % 1×D
    wC = sum(w .* cos(Theta), 1);            % 1×D
    % N×D coupling matrix (self-term = 0, no correction needed)
    C  = wS .* cos(Theta) - wC .* sin(Theta);

    % Global attractor pull  sin(θ* − θ_i)
    A  = sin(theta_best - Theta);            % N×D

    % Quantum noise
    noise = randn(N, D);

    % Full update
    dTheta = K_t * opts.eta * C + opts.eta_g * A + sigma_t * noise;
    Theta_new = Theta + dTheta;

    % ── (6) Elastic reflection into [0, π/2]                [Eq. 6]
    Theta_new = qhw_reflect(Theta_new, 0, HP);

    % ── Collapse: decode → evaluate
    X_new = qhw_decode(Theta_new, lb, ub);
    F_new = qhw_eval(fun, X_new);
    NFE   = NFE + N;

    % ── Greedy selection
    better = F_new < F;
    Theta(better,:) = Theta_new(better,:);
    X(better,:)     = X_new(better,:);
    F(better)       = F_new(better);

    % ── Update global best
    [cur_best, ci] = min(F);
    if cur_best < f_best - opts.tol
        f_best     = cur_best;
        x_best     = X(ci, :);
        theta_best = Theta(ci, :);
        stall_cnt  = 0;
    else
        stall_cnt  = stall_cnt + 1;
    end

    % ── (8) Quantum tunneling                               [Eq. 8]
    if rand() < opts.p_tun
        n_tun = max(1, round(opts.q_tun * N));
        [~, sidx] = sort(F, 'descend');
        worst = sidx(1:n_tun);
        Theta(worst,:) = rand(n_tun, D) * HP;
        X(worst,:)     = qhw_decode(Theta(worst,:), lb, ub);
        F(worst)       = qhw_eval(fun, X(worst,:));
        NFE = NFE + n_tun;
        [new_best, ni] = min(F);
        if new_best < f_best
            f_best = new_best;  x_best = X(ni,:);  theta_best = Theta(ni,:);
        end
    end

    % ── (7) Noise annealing                                 [Eq. 7]
    sigma_t = max(opts.sigma_min, sigma_t * opts.alpha);

    % ── Record
    hist_best(t)  = f_best;
    hist_mean(t)  = mean(F);
    hist_r(t)     = r_t;
    hist_sigma(t) = sigma_t;
    hist_NFE(t)   = NFE;

    if opts.verbose && (t==1 || mod(t,50)==0 || t==T)
        fprintf('  %-6d  %-14.6g  %-12.6g  %-7.4f  %-7.5f\n', ...
                t, f_best, mean(F), r_t, sigma_t);
    end

    % ── Early stopping
    if stall_cnt >= opts.max_stall
        if opts.verbose
            fprintf('  [Convergencia: gen=%d, estancamiento=%d]\n', t, stall_cnt);
        end
        T_actual = t;
        break;
    end
end

if opts.verbose
    fprintf('  %s\n', repmat('─',1,52));
    fprintf('  f* = %-14.8g   (NFE=%d, generaciones=%d)\n\n', f_best, NFE, T_actual);
end

% Output
info.hist_best   = hist_best(1:T_actual);
info.hist_mean   = hist_mean(1:T_actual);
info.hist_r      = hist_r(1:T_actual);
info.hist_sigma  = hist_sigma(1:T_actual);
info.hist_NFE    = hist_NFE(1:T_actual);
info.NFE         = NFE;
info.generations = T_actual;
info.Theta_final = Theta;
info.F_final     = F;

end % ── QHW ──────────────────────────────────────────────────────────────────

% =============================================================================
%  LOCAL SUBFUNCTIONS
% =============================================================================

function X = qhw_decode(Theta, lb, ub)
% x_iᵏ = lb_k + (ub_k − lb_k)·sin²(θ_iᵏ)    [Eq. 1]
    X = lb + (ub - lb) .* sin(Theta).^2;
end

function Theta = qhw_reflect(Theta, lo, hi)
% Elastic reflection to keep θ ∈ [lo, hi]
    range = hi - lo;
    Theta = Theta - lo;
    Theta = mod(Theta, 2*range);
    over = Theta > range;
    Theta(over) = 2*range - Theta(over);
    Theta = Theta + lo;
end

function F = qhw_eval(fun, X)
% Evaluate objective for all N rows of X
    N = size(X, 1);
    F = zeros(N, 1);
    for i = 1:N
        val = fun(X(i,:));
        F(i) = val(1);  % ensure scalar
    end
end
