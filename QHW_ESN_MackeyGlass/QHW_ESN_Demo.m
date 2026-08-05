%% QHW_ESN_Demo.m
%  Aplicación del optimizador Q-HW para ajuste de hiperparámetros de una
%  Echo State Network (ESN) en la predicción de la serie caótica de Mackey-Glass.
%
%  Este script demuestra la aplicabilidad del optimizador genérico QHW.m
%  a un problema de optimización real en aprendizaje de máquinas.
%
%  Parámetros ESN optimizados:
%    θ₁  →  ρ       radio espectral         [0.10, 1.50]
%    θ₂  →  α_in    escala de entrada       [0.01, 2.00]
%    θ₃  →  λ       tasa de fuga (leak)     [0.10, 1.00]
%    θ₄  →  log₁₀β  regularización ridge   [-6.0, 0.00]
%
%  César Valencia — 2026

clear; clc; close all;
rng(42);

%% ─── GENERAR MACKEY-GLASS ───────────────────────────────────────────────────
N_series = 3000;
tau      = 17;      % tau=17 → comportamiento caótico estándar
H        = 1;       % horizonte de predicción (pasos adelante)

ts = mackeyglass(N_series, tau);
ts = 2*(ts - min(ts))/(max(ts)-min(ts)) - 1;   % normalizar a [-1, 1]

X_all = ts(1:end-H);
Y_all = ts(1+H:end);
N     = numel(X_all);

n_tr = floor(0.60*N);
n_vl = floor(0.20*N);
X_tr = X_all(1:n_tr);           Y_tr = Y_all(1:n_tr);
X_vl = X_all(n_tr+1:n_tr+n_vl); Y_vl = Y_all(n_tr+1:n_tr+n_vl);
X_te = X_all(n_tr+n_vl+1:end);  Y_te = Y_all(n_tr+n_vl+1:end);

%% ─── CONSTRUIR RESERVORIO FIJO ──────────────────────────────────────────────
Nr      = 200;
density = 0.10;
[W_res, W_in_base] = build_reservoir(Nr, density);

%% ─── FUNCIÓN OBJETIVO PARA Q-HW ─────────────────────────────────────────────
%  El optimizador recibe x = [rho, alpha_in, lambda, log10(beta)]
%  y devuelve RMSE en el conjunto de validación.
%  Esta es la única interfaz necesaria: fun(x) → scalar
fitness = @(x) esn_rmse(x, W_res, W_in_base, X_tr, Y_tr, X_vl, Y_vl);

lb = [0.10, 0.01, 0.10, -6.0];
ub = [1.50, 2.00, 1.00,  0.0];

%% ─── CONFIGURAR Y EJECUTAR Q-HW ─────────────────────────────────────────────
opts = struct();
opts.N         = 30;
opts.T         = 200;
opts.eta       = 0.30;
opts.eta_g     = 0.10;
opts.K_min     = 0.05;
opts.K_max     = 1.00;
opts.gamma     = 5.0;
opts.sigma0    = 0.10;
opts.sigma_min = 0.001;
opts.alpha     = 0.97;
opts.p_tun     = 0.05;
opts.q_tun     = 0.10;
opts.max_stall = 60;
opts.seed      = 42;
opts.verbose   = true;

[x_opt, rmse_val, info] = QHW(fitness, lb, ub, opts);

%% ─── RESULTADOS ─────────────────────────────────────────────────────────────
fprintf('═══════════════════════════════════════════\n');
fprintf('  PARÁMETROS ESN ÓPTIMOS (Q-HW)\n');
fprintf('───────────────────────────────────────────\n');
fprintf('  ρ       = %.4f  (radio espectral)\n',   x_opt(1));
fprintf('  α_in    = %.4f  (escala entrada)\n',    x_opt(2));
fprintf('  λ       = %.4f  (leak rate)\n',         x_opt(3));
fprintf('  β       = %.2e  (regularización)\n',    10^x_opt(4));
fprintf('  RMSE_val= %.6f\n', rmse_val);
fprintf('═══════════════════════════════════════════\n');

%% Entrenar con train+val, evaluar en test
[Y_pred, rmse_te, nrmse_te, mae_te] = esn_predict( ...
    x_opt, W_res, W_in_base, [X_tr;X_vl], [Y_tr;Y_vl], X_te, Y_te);

fprintf('\n  MÉTRICAS EN TEST:\n');
fprintf('  RMSE  = %.6f\n', rmse_te);
fprintf('  NRMSE = %.6f\n', nrmse_te);
fprintf('  MAE   = %.6f\n', mae_te);

%% ─── VISUALIZACIONES ────────────────────────────────────────────────────────
fig = figure('Name','Q-HW + ESN — Mackey-Glass','NumberTitle','off', ...
             'Position',[40 40 1500 900]);

% (1) Serie completa
subplot(3,3,[1 2 3]);
t_all = 1:N;
plot(1:n_tr, Y_tr,'b','LineWidth',0.8); hold on;
plot(n_tr+1:n_tr+n_vl, Y_vl,'g','LineWidth',0.8);
plot(n_tr+n_vl+1:N, Y_te,'k','LineWidth',1.2);
xline(n_tr,       '--r','LineWidth',1.2,'Label','Fin Train');
xline(n_tr+n_vl,  '--m','LineWidth',1.2,'Label','Fin Val');
title('Serie Mackey-Glass (τ=17, normalizada)','FontWeight','bold');
legend('Train','Validación','Test','Location','best');
xlabel('t'); ylabel('x(t)'); grid on;

% (2) Convergencia f_best y media
subplot(3,3,4);
semilogy(info.hist_NFE, info.hist_best,'r-','LineWidth',2); hold on;
semilogy(info.hist_NFE, info.hist_mean,'b--','LineWidth',1.2);
xlabel('NFE'); ylabel('RMSE (val, log)');
title('Convergencia Q-HW'); grid on;
legend('Mejor','Media');

% (3) Parámetro de orden Kuramoto r(t)
subplot(3,3,5);
yyaxis left
semilogy(info.hist_NFE, info.hist_best,'b-','LineWidth',1.5);
ylabel('RMSE_{val}','Color','b');
yyaxis right
plot(info.hist_NFE, info.hist_r,'r-','LineWidth',1.5);
ylabel('r(t) — Kuramoto','Color','r'); ylim([0 1]);
xlabel('NFE');
title('Sincronización osciladores'); grid on;

% (4) Predicción vs real (test)
subplot(3,3,[6 7]);
n_te = numel(Y_te);
plot(1:n_te, Y_te,'k','LineWidth',1.2); hold on;
plot(1:n_te, Y_pred,'r--','LineWidth',1.2);
title(sprintf('Predicción en Test  (NRMSE=%.5f)', nrmse_te),'FontWeight','bold');
legend('Real','Q-HW+ESN'); xlabel('t'); ylabel('x(t)'); grid on;

% (5) Scatter real vs predicho
subplot(3,3,8);
scatter(Y_te, Y_pred, 12, 'filled','MarkerFaceAlpha',0.4,'MarkerFaceColor',[0.2 0.5 0.9]);
hold on; lm = [min(Y_te) max(Y_te)];
plot(lm, lm,'r--','LineWidth',1.5);
xlabel('Real'); ylabel('Predicho'); title('Scatter test'); grid on; axis equal;
r2 = corr(Y_te, Y_pred)^2;
text(min(lm)+0.05*(lm(2)-lm(1)), max(lm)-0.1*(lm(2)-lm(1)), ...
     sprintf('R²=%.4f',r2),'FontSize',10,'Color','r');

% (6) Error absoluto
subplot(3,3,9);
plot(1:n_te, abs(Y_te - Y_pred),'Color',[0.8 0.3 0]);
xlabel('t'); ylabel('|error|'); title('Error absoluto (test)'); grid on;

sgtitle(sprintf('Q-HW + ESN  |  Mackey-Glass (τ=%d, H=%d)  |  Test NRMSE=%.5f', ...
        tau, H, nrmse_te), 'FontSize',13,'FontWeight','bold');

%% Figura: distribución de fases finales (diagrama Kuramoto)
fig2 = figure('Name','Distribución de Fases — Población Final Q-HW', ...
              'NumberTitle','off','Position',[40 1000 900 400]);
pnames = {'\rho','\alpha_{in}','\lambda','log_{10}(\beta)'};
Theta_f = info.Theta_final;
for k = 1:4
    subplot(1,4,k);
    th = Theta_f(:,k);
    polarhistogram(th, 12, 'FaceColor',[0.2 0.5 0.9],'EdgeColor','w','FaceAlpha',0.7);
    title(pnames{k},'FontSize',11,'FontWeight','bold');
end
sgtitle('Fases cuánticas θ^k — Población final Q-HW','FontSize',11);

%% ═══════════════════════════════════════════════════════════════════════════
%%  SUBFUNCIONES
%% ═══════════════════════════════════════════════════════════════════════════

function ts = mackeyglass(N, tau)
% Integración Euler de dx/dt = 0.2·x(t−τ)/(1+x(t−τ)^10) − 0.1·x(t)
    ts = zeros(N + tau, 1);
    ts(1:tau) = 0.9;
    for t = tau+1:N+tau
        xt = ts(t-tau);
        ts(t) = ts(t-1) + 0.2*xt/(1+xt^10) - 0.1*ts(t-1);
    end
    ts = ts(tau+1:end);
end

function [W_res, W_in] = build_reservoir(Nr, dens)
% Reservorio disperso con radio espectral normalizado a 1
    W = (rand(Nr) < dens) .* randn(Nr);
    ev = abs(eig(W));
    W_res = W / max(ev + 1e-12);
    W_in  = randn(Nr, 1);
end

function rmse = esn_rmse(params, W_res, W_in_base, X_tr, Y_tr, X_vl, Y_vl)
% Entrena ESN en train, evalúa RMSE en validación
    rho = params(1);  ain = params(2);  lk = params(3);  breg = 10^params(4);
    Nr  = size(W_res,1);
    W   = W_res * rho;
    Win = W_in_base * ain;

    n = numel(X_tr);
    H = zeros(n, Nr);
    x = zeros(Nr,1);
    for t = 1:n
        x = (1-lk)*x + lk*tanh(W*x + Win*X_tr(t));
        H(t,:) = x';
    end
    Wout = (H'*H + breg*eye(Nr)) \ (H'*Y_tr);

    nv = numel(X_vl);
    Yp = zeros(nv,1);
    for t = 1:nv
        x = (1-lk)*x + lk*tanh(W*x + Win*X_vl(t));
        Yp(t) = Wout'*x;
    end
    rmse = sqrt(mean((Y_vl - Yp).^2));
    if ~isfinite(rmse), rmse = 1e6; end
end

function [Y_pred, rmse, nrmse, mae] = esn_predict( ...
        params, W_res, W_in_base, X_tv, Y_tv, X_te, Y_te)
% Re-entrena con train+val, predice en test
    rho = params(1);  ain = params(2);  lk = params(3);  breg = 10^params(4);
    Nr  = size(W_res,1);
    W   = W_res * rho;
    Win = W_in_base * ain;

    n = numel(X_tv);
    H = zeros(n, Nr);
    x = zeros(Nr,1);
    for t = 1:n
        x = (1-lk)*x + lk*tanh(W*x + Win*X_tv(t));
        H(t,:) = x';
    end
    Wout = (H'*H + breg*eye(Nr)) \ (H'*Y_tv);

    nt = numel(X_te);
    Y_pred = zeros(nt,1);
    for t = 1:nt
        x = (1-lk)*x + lk*tanh(W*x + Win*X_te(t));
        Y_pred(t) = Wout'*x;
    end
    rmse  = sqrt(mean((Y_te - Y_pred).^2));
    nrmse = rmse / std(Y_te);
    mae   = mean(abs(Y_te - Y_pred));
end
