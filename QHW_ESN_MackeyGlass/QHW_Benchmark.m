%% QHW_Benchmark.m
%  Evaluación estadística del optimizador Q-HW sobre funciones de prueba
%  estándar de la literatura de optimización global.
%
%  Algoritmos comparados:
%    Q-HW  — Quantum-inspired Harmonic Wave (propuesto)
%    PSO   — Particle Swarm Optimization (Kennedy & Eberhart, 1995)
%    DE    — Differential Evolution DE/rand/1/bin (Storn & Price, 1997)
%    QIEA  — Quantum-Inspired Evolutionary Algorithm continuo (Han & Kim, 2002)
%
%  Protocolo experimental:
%    - D = 10 dimensiones
%    - N = 30 individuos
%    - MaxFE = 30 000 evaluaciones de función (budget fijo)
%    - 30 ejecuciones independientes por algoritmo por función
%    - Análisis estadístico: media ± desv.std., mejor, peor
%    - Test de Wilcoxon (α=0.05): Q-HW vs cada baseline
%
%  Funciones de prueba (clásicas en CEC/IEEE):
%    F1 Sphere        unimodal, separable, convexa
%    F2 Rosenbrock    unimodal, no-separable, valle estrecho
%    F3 Rastrigin     multimodal, altamente engañosa (10D·10n mínimos)
%    F4 Ackley        multimodal, quasi-plana con mínimo global profundo
%    F5 Schwefel      multimodal, mínimo engañoso alejado del centro
%    F6 Griewank      multimodal, interferencia multiplicativa
%
%  César Valencia — 2026

clear; clc; close all;

%% ─── PARÁMETROS EXPERIMENTALES ─────────────────────────────────────────────
D      = 10;
N_pop  = 30;
MaxFE  = 30000;
T      = floor(MaxFE / N_pop);   % generaciones equivalentes
N_runs = 30;

rng_seeds = 1:N_runs;   % semillas reproducibles

%% ─── DEFINICIÓN DE FUNCIONES DE PRUEBA ─────────────────────────────────────
functions = define_benchmark_functions(D);
nF = numel(functions);

alg_names = {'Q-HW', 'PSO', 'DE', 'QIEA-C'};
nA = numel(alg_names);

% Almacén de resultados: nA × nF × N_runs
results = nan(nA, nF, N_runs);

%% ─── OPCIONES COMPARTIDAS ────────────────────────────────────────────────────
qhw_opts = struct('N', N_pop, 'T', T, 'verbose', false, ...
                  'eta',0.30,'eta_g',0.10,'K_min',0.05,'K_max',1.0, ...
                  'gamma',5.0,'sigma0',0.10,'sigma_min',0.001,'alpha',0.97, ...
                  'p_tun',0.05,'q_tun',0.10,'max_stall',999);

%% ─── EXPERIMENTOS ────────────────────────────────────────────────────────────
fprintf('Ejecutando benchmark: %d funciones × %d algoritmos × %d corridas\n', ...
        nF, nA, N_runs);
fprintf('Presupuesto: MaxFE=%d  (N=%d, T=%d)\n\n', MaxFE, N_pop, T);

for fi = 1:nF
    fn   = functions(fi);
    lb_f = fn.lb * ones(1,D);
    ub_f = fn.ub * ones(1,D);

    fprintf('F%d: %-12s  [%.1f, %.1f]^%d  f*=%.2f\n', ...
            fi, fn.name, fn.lb, fn.ub, D, fn.fopt);

    for run = 1:N_runs
        seed_r = rng_seeds(run);

        % Q-HW
        qhw_opts.seed = seed_r;
        [~, fb] = QHW(fn.fun, lb_f, ub_f, qhw_opts);
        results(1, fi, run) = fb - fn.fopt;

        % PSO
        rng(seed_r);
        [~, fb] = run_PSO(fn.fun, lb_f, ub_f, N_pop, T);
        results(2, fi, run) = fb - fn.fopt;

        % DE
        rng(seed_r);
        [~, fb] = run_DE(fn.fun, lb_f, ub_f, N_pop, T);
        results(3, fi, run) = fb - fn.fopt;

        % QIEA-C
        rng(seed_r);
        [~, fb] = run_QIEA(fn.fun, lb_f, ub_f, N_pop, T);
        results(4, fi, run) = fb - fn.fopt;
    end
    fprintf('   Listo.\n');
end

%% ─── TABLA DE RESULTADOS ─────────────────────────────────────────────────────
fprintf('\n%s\n', repmat('═',1,95));
fprintf('  TABLA DE RESULTADOS  (f_best − f*)  D=%d, N=%d, MaxFE=%d, %d corridas\n', ...
        D, N_pop, MaxFE, N_runs);
fprintf('%s\n', repmat('═',1,95));

hdr = '  %-12s | %-22s | %-22s | %-22s | %-22s';
fprintf([hdr '\n'], 'Función', 'Q-HW (propuesto)', 'PSO', 'DE', 'QIEA-C');
fprintf('  %s\n', repmat('-',1,93));
sub = '  %-12s | %-22s | %-22s | %-22s | %-22s';

for fi = 1:nF
    fn = functions(fi);
    row_strs = cell(1, nA);
    for ai = 1:nA
        r = squeeze(results(ai, fi, :));
        row_strs{ai} = sprintf('%.2e ± %.2e', mean(r), std(r));
    end
    fprintf([sub '\n'], fn.name, row_strs{:});
end
fprintf('%s\n\n', repmat('═',1,95));

%% ─── TEST WILCOXON (Q-HW vs. baselines) ─────────────────────────────────────
alpha_w = 0.05;
fprintf('  Test Wilcoxon rank-sum (H₀: igualdad de medianas, α=%.2f)\n', alpha_w);
fprintf('  Resultado: "+" Q-HW mejor  |  "=" sin diferencia  |  "-" Q-HW peor\n\n');
fprintf('  %-12s | %-10s | %-10s | %-10s\n', 'Función','vs PSO','vs DE','vs QIEA-C');
fprintf('  %s\n', repmat('-',1,50));

wilcoxon_table = cell(nF, nA-1);
for fi = 1:nF
    r_qhw = squeeze(results(1, fi, :));
    fn = functions(fi);
    row_str = '';
    for ai = 2:nA
        r_base = squeeze(results(ai, fi, :));
        if exist('ranksum','file')
            [p, ~] = ranksum(r_qhw, r_base);
        else
            % Approximate: Mann-Whitney via rank sum
            p = mannwhitney_approx(r_qhw, r_base);
        end
        if p < alpha_w
            if median(r_qhw) < median(r_base), sym = '+'; else, sym = '-'; end
        else
            sym = '=';
        end
        wilcoxon_table{fi, ai-1} = sprintf('%s (p=%.3f)', sym, p);
        row_str = [row_str, sprintf(' %-10s |', wilcoxon_table{fi,ai-1})]; %#ok
    end
    fprintf('  %-12s |%s\n', fn.name, row_str);
end
fprintf('\n');

%% ─── SCORE GLOBAL ───────────────────────────────────────────────────────────
wins  = zeros(1, nA);
for fi = 1:nF
    means = mean(results(:,fi,:), 3);
    [~, winner] = min(means);
    wins(winner) = wins(winner) + 1;
end
fprintf('  Funciones ganadas (menor media): ');
for ai = 1:nA
    fprintf('%s=%d  ', alg_names{ai}, wins(ai));
end
fprintf('\n\n');

%% ─── CURVAS DE CONVERGENCIA ─────────────────────────────────────────────────
fprintf('Generando curvas de convergencia (una corrida representativa)...\n');

colors = {[0.1 0.5 0.9], [0.9 0.3 0.1], [0.1 0.7 0.3], [0.7 0.1 0.7]};

fig_conv = figure('Name','Q-HW Benchmark — Convergencia','NumberTitle','off', ...
                  'Position',[30 30 1400 800]);

for fi = 1:nF
    fn   = functions(fi);
    lb_f = fn.lb * ones(1,D);
    ub_f = fn.ub * ones(1,D);

    subplot(2, 3, fi);
    hold on; box on; grid on;

    % Q-HW
    qhw_opts.seed = 1;
    [~, ~, info_qhw] = QHW(fn.fun, lb_f, ub_f, qhw_opts);
    plot(info_qhw.hist_NFE, max(info_qhw.hist_best - fn.fopt, 1e-15), ...
         '-','Color',colors{1},'LineWidth',2.0,'DisplayName','Q-HW');

    % PSO
    rng(1);
    [~, ~, hist_pso] = run_PSO(fn.fun, lb_f, ub_f, N_pop, T, true);
    plot(N_pop*(1:numel(hist_pso)), max(hist_pso - fn.fopt, 1e-15), ...
         '--','Color',colors{2},'LineWidth',1.5,'DisplayName','PSO');

    % DE
    rng(1);
    [~, ~, hist_de] = run_DE(fn.fun, lb_f, ub_f, N_pop, T, true);
    plot(N_pop*(1:numel(hist_de)), max(hist_de - fn.fopt, 1e-15), ...
         ':','Color',colors{3},'LineWidth',1.5,'DisplayName','DE');

    % QIEA-C
    rng(1);
    [~, ~, hist_q] = run_QIEA(fn.fun, lb_f, ub_f, N_pop, T, true);
    plot(N_pop*(1:numel(hist_q)), max(hist_q - fn.fopt, 1e-15), ...
         '-.','Color',colors{4},'LineWidth',1.5,'DisplayName','QIEA-C');

    set(gca,'YScale','log');
    xlabel('NFE'); ylabel('f − f*');
    title(sprintf('F%d: %s', fi, fn.name), 'FontWeight','bold');
    if fi == 1, legend('Location','northeast','FontSize',8); end
end

sgtitle(sprintf('Convergencia — D=%d, N=%d', D, N_pop), ...
        'FontSize',13,'FontWeight','bold');

%% ─── DIAGRAMA DE PARÁMETROS KURAMOTO (orden r(t) para una función) ──────────
fig_kuramoto = figure('Name','Q-HW — Parámetro de Orden Kuramoto','NumberTitle','off', ...
                      'Position',[30 900 900 350]);

fn_demo = functions(3);  % Rastrigin (más interesante)
lb_f = fn_demo.lb * ones(1,D);
ub_f = fn_demo.ub * ones(1,D);
qhw_opts.seed = 1;
[~, ~, info_k] = QHW(fn_demo.fun, lb_f, ub_f, qhw_opts);

yyaxis left
plot(info_k.hist_NFE, info_k.hist_best, 'b-', 'LineWidth',2);
ylabel('f_{best}','Color','b');
yyaxis right
plot(info_k.hist_NFE, info_k.hist_r, 'r--', 'LineWidth',1.8);
ylabel('r(t) — Parámetro de Orden Kuramoto','Color','r');
xlabel('NFE');
title(sprintf('Sincronización cuántica — %s (D=%d)', fn_demo.name, D));
legend({'f_{best}','r(t)'},'Location','east');
grid on;
annotation('textbox',[0.55 0.20 0.35 0.15], ...
    'String',{'r(t)→0: exploración (incoherente)','r(t)→1: explotación (sincronizado)'}, ...
    'EdgeColor','none','FontSize',8,'Color',[0.3 0.3 0.3]);

fprintf('Benchmark completo.\n');

%% ═══════════════════════════════════════════════════════════════════════════
%%  FUNCIONES DE PRUEBA
%% ═══════════════════════════════════════════════════════════════════════════
function fns = define_benchmark_functions(D)
    fns(1) = struct('name','Sphere',    'lb',-5.12,'ub', 5.12,'fopt',0, ...
        'fun', @(x) sum(x.^2));
    fns(2) = struct('name','Rosenbrock','lb',-2.048,'ub', 2.048,'fopt',0, ...
        'fun', @(x) sum(100*(x(2:end)-x(1:end-1).^2).^2 + (1-x(1:end-1)).^2));
    fns(3) = struct('name','Rastrigin', 'lb',-5.12,'ub', 5.12,'fopt',0, ...
        'fun', @(x) 10*D + sum(x.^2 - 10*cos(2*pi*x)));
    fns(4) = struct('name','Ackley',    'lb',-32.0,'ub', 32.0,'fopt',0, ...
        'fun', @(x) -20*exp(-0.2*sqrt(mean(x.^2))) - exp(mean(cos(2*pi*x))) + 20 + exp(1));
    fns(5) = struct('name','Schwefel',  'lb',-500, 'ub', 500, 'fopt',0, ...
        'fun', @(x) 418.9829*D - sum(x.*sin(sqrt(abs(x)))));
    fns(6) = struct('name','Griewank',  'lb',-600, 'ub', 600, 'fopt',0, ...
        'fun', @(x) 1 + sum(x.^2)/4000 - prod(cos(x./sqrt(1:D))));
end

%% ═══════════════════════════════════════════════════════════════════════════
%%  ALGORITMOS BASELINE
%% ═══════════════════════════════════════════════════════════════════════════

function [x_best, f_best, hist] = run_PSO(fun, lb, ub, N, T, return_hist)
%RUN_PSO  Standard PSO (Clerc & Kennedy, 2002 constriction factor).
%  w=0.7298, c1=c2=1.4962
    if nargin < 6, return_hist = false; end
    D  = numel(lb);
    w  = 0.7298;  c1 = 1.4962;  c2 = 1.4962;
    Vmax = (ub - lb) * 0.2;

    X  = lb + (ub-lb) .* rand(N, D);
    V  = zeros(N, D);
    F  = arrayfun(@(i) fun(X(i,:)), 1:N)';

    pbest_X = X;
    pbest_F = F;
    [f_best, gi] = min(F);
    x_best = X(gi,:);

    hist = zeros(T, 1);
    for t = 1:T
        r1 = rand(N,D);  r2 = rand(N,D);
        V  = w*V + c1*r1.*(pbest_X-X) + c2*r2.*(x_best - X);
        V  = max(min(V, Vmax), -Vmax);
        X  = X + V;
        X  = max(min(X, ub), lb);
        Fn = arrayfun(@(i) fun(X(i,:)), 1:N)';
        better = Fn < pbest_F;
        pbest_X(better,:) = X(better,:);
        pbest_F(better)   = Fn(better);
        [cur, ci] = min(pbest_F);
        if cur < f_best, f_best = cur; x_best = pbest_X(ci,:); end
        hist(t) = f_best;
    end
    if ~return_hist, hist = []; end
end

function [x_best, f_best, hist] = run_DE(fun, lb, ub, N, T, return_hist)
%RUN_DE  Differential Evolution DE/rand/1/bin (Storn & Price, 1997).
%  F_scale=0.8, CR=0.9
    if nargin < 6, return_hist = false; end
    D  = numel(lb);
    Fs = 0.8;  CR = 0.9;

    X = lb + (ub-lb) .* rand(N, D);
    F_pop = arrayfun(@(i) fun(X(i,:)), 1:N)';
    [f_best, bi] = min(F_pop);
    x_best = X(bi,:);

    hist = zeros(T, 1);
    for t = 1:T
        for i = 1:N
            % Mutation: pick 3 distinct indices ≠ i
            idx = randperm(N, 4);
            idx(idx==i) = [];
            r1=idx(1); r2=idx(2); r3=idx(3);
            V  = X(r1,:) + Fs*(X(r2,:) - X(r3,:));
            V  = max(min(V, ub), lb);
            % Crossover
            mask = rand(1,D) < CR;
            if ~any(mask), mask(randi(D)) = true; end
            U = X(i,:);  U(mask) = V(mask);
            % Selection
            fU = fun(U);
            if fU < F_pop(i)
                X(i,:) = U;  F_pop(i) = fU;
                if fU < f_best, f_best = fU; x_best = U; end
            end
        end
        hist(t) = f_best;
    end
    if ~return_hist, hist = []; end
end

function [x_best, f_best, hist] = run_QIEA(fun, lb, ub, N, T, return_hist)
%RUN_QIEA  Continuous QIEA (quantum rotation gate, Han & Kim 2002 extension).
%  Update: Δθ = Δθ_max · sign(θ* − θ_i)  with adaptive Δθ_max
    if nargin < 6, return_hist = false; end
    D     = numel(lb);
    HP    = pi/2;
    DTmax = 0.05 * HP;  % max rotation angle

    Theta = rand(N, D) * HP;
    X     = lb + (ub-lb) .* sin(Theta).^2;
    F_pop = arrayfun(@(i) fun(X(i,:)), 1:N)';

    [f_best, bi] = min(F_pop);
    x_best = X(bi,:);
    theta_best = Theta(bi,:);

    hist = zeros(T, 1);
    for t = 1:T
        DT = DTmax * sign(theta_best - Theta) + 0.01*randn(N,D);
        Theta_new = Theta + DT;
        Theta_new = max(min(Theta_new, HP), 0);
        X_new = lb + (ub-lb) .* sin(Theta_new).^2;
        F_new = arrayfun(@(i) fun(X_new(i,:)), 1:N)';
        better = F_new < F_pop;
        Theta(better,:) = Theta_new(better,:);
        X(better,:)     = X_new(better,:);
        F_pop(better)   = F_new(better);
        [cur, ci] = min(F_pop);
        if cur < f_best
            f_best = cur; x_best = X(ci,:); theta_best = Theta(ci,:);
        end
        hist(t) = f_best;
    end
    if ~return_hist, hist = []; end
end

function p = mannwhitney_approx(x, y)
% Approximate two-sided Mann-Whitney p-value using normal approximation
    nx = numel(x); ny = numel(y);
    all_v = [x(:); y(:)];
    [~, ~, ranks] = unique(all_v);
    rx = sum(ranks(1:nx));
    mu_r = nx*(nx+ny+1)/2;
    sig_r = sqrt(nx*ny*(nx+ny+1)/12);
    z = (rx - mu_r) / sig_r;
    p = 2*(1 - normcdf(abs(z)));
end
