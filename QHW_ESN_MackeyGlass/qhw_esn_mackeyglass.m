%% Q-HW: Quantum-inspired Harmonic Wave Optimizer
%  Optimiza parámetros de una Echo State Network (ESN)
%  para predicción de la serie de Mackey-Glass sintética.
%
%  Metáfora física implementada:
%    - Cada candidato i = oscilador cuántico con ángulos de fase θ_i ∈ [0, π/2]
%    - Parámetro real: p_i^k = p_min^k + (p_max^k - p_min^k)·sin²(θ_i^k)
%    - Fitness → "fuerza del golpe" → peso en el acoplamiento
%    - Regla de actualización: Kuramoto + rotación cuántica
%      Δθ_i^k = η · Σ_j w_j · sin(θ_j^k − θ_i^k) + σ · randn
%    - Interferencia constructiva → convergencia; destructiva → descarte
%
%  Parámetros ESN optimizados: [ρ, α, λ, log10(β)]
%    ρ : radio espectral       [0.1 , 1.50]
%    α : escala de entrada     [0.01, 2.00]
%    λ : tasa de fuga (leak)   [0.10, 1.00]
%    β : regularización (log)  [-6  , 0   ]
%
%  César Valencia — 2026

clear; clc; close all;
rng(42);  % reproducibilidad

%% ─── CONFIGURACIÓN GLOBAL ──────────────────────────────────────────────────

% Mackey-Glass
MG.N      = 3000;   % puntos totales
MG.tau    = 17;     % retardo clásico (caótico)
MG.beta   = 0.2;
MG.gamma  = 0.1;
MG.n      = 10;
MG.dt     = 1.0;
MG.H      = 1;      % horizonte de predicción (pasos adelante)

% División train/val/test
SPLIT.train = 0.60;
SPLIT.val   = 0.20;
% resto = test

% ESN (estructura fija, solo escala cambia)
ESN.Nr     = 200;   % neuronas en el reservorio
ESN.density = 0.10; % densidad de conexiones del reservorio

% Q-HW — Parámetros del optimizador
QHW.Npop   = 30;    % tamaño de población
QHW.Tmax   = 150;   % iteraciones máximas
QHW.eta    = 0.25;  % tasa de aprendizaje (fuerza de acoplamiento K/N)
QHW.sigma  = 0.05;  % ruido cuántico (exploración)
QHW.sigma_min = 0.005; % ruido mínimo (enfriamiento)
QHW.alpha_decay = 0.97; % decaimiento del ruido por iteración

% Límites de parámetros ESN [min, max] por dimensión
BOUNDS = [0.10, 1.50;   % rho  (radio espectral)
          0.01, 2.00;   % alpha_in (escala entrada)
          0.10, 1.00;   % lambda (leak rate)
          -6.0, 0.00];  % log10(beta)  regularización
Ndim = size(BOUNDS, 1);

%% ─── 1. GENERAR SERIE MACKEY-GLASS ─────────────────────────────────────────
fprintf('Generando serie Mackey-Glass (N=%d, tau=%d)...\n', MG.N, MG.tau);
ts = mackey_glass_gen(MG.N, MG.tau, MG.beta, MG.gamma, MG.n, MG.dt);

% Normalizar a [-1, 1]
ts_min = min(ts); ts_max = max(ts);
ts_norm = 2*(ts - ts_min)/(ts_max - ts_min) - 1;

% Construir pares (entrada, salida) con horizonte H
X_all = ts_norm(1 : end - MG.H);
Y_all = ts_norm(1+MG.H : end);
Ntotal = length(X_all);

% Dividir
n_train = floor(SPLIT.train * Ntotal);
n_val   = floor(SPLIT.val   * Ntotal);
n_test  = Ntotal - n_train - n_val;

X_train = X_all(1 : n_train);
Y_train = Y_all(1 : n_train);
X_val   = X_all(n_train+1 : n_train+n_val);
Y_val   = Y_all(n_train+1 : n_train+n_val);
X_test  = X_all(n_train+n_val+1 : end);
Y_test  = Y_all(n_train+n_val+1 : end);

fprintf('  Train: %d | Val: %d | Test: %d muestras\n', n_train, n_val, n_test);

%% ─── 2. CONSTRUIR RESERVORIO FIJO ──────────────────────────────────────────
fprintf('Construyendo reservorio ESN (Nr=%d)...\n', ESN.Nr);
[W_res, W_in_base] = build_reservoir(ESN.Nr, ESN.density);

%% ─── 3. FUNCIÓN DE FITNESS ──────────────────────────────────────────────────
% Evalúa RMSE en el conjunto de validación dado un vector de parámetros ESN
fitness_fn = @(params) esn_fitness(params, W_res, W_in_base, ...
                                    X_train, Y_train, X_val, Y_val, BOUNDS);

%% ─── 4. INICIALIZACIÓN Q-HW ────────────────────────────────────────────────
fprintf('\nIniciando Q-HW (Npop=%d, Tmax=%d)...\n', QHW.Npop, QHW.Tmax);

% Ángulos θ ∈ [0, π/2] — representación cuántica (qubit generalizado)
Theta = rand(QHW.Npop, Ndim) * (pi/2);  % superposición inicial uniforme

% Decodificar a parámetros reales
Params = decode_theta(Theta, BOUNDS);

% Evaluar fitness inicial
Fitness = zeros(QHW.Npop, 1);
for i = 1:QHW.Npop
    Fitness(i) = fitness_fn(Params(i,:));
end

% Mejor global
[best_fit, best_idx] = min(Fitness);
best_params = Params(best_idx, :);
best_theta  = Theta(best_idx, :);

history_best = zeros(QHW.Tmax, 1);
history_mean = zeros(QHW.Tmax, 1);

sigma_t = QHW.sigma;  % ruido actual (decrece)

%% ─── 5. BUCLE PRINCIPAL Q-HW ────────────────────────────────────────────────
fprintf('%-6s %-12s %-12s %-10s %-10s %-10s %-10s\n', ...
        'Iter','Best RMSE','Mean RMSE','rho','alpha','leak','log10(b)');
fprintf('%s\n', repmat('-',1,72));

for t = 1:QHW.Tmax

    %% 5a. Calcular pesos de acoplamiento (fuerza del golpe)
    %     w_i ∝ 1/RMSE_i  (mejor solución → mayor influencia)
    inv_fit = 1 ./ (Fitness + 1e-12);
    weights = inv_fit / sum(inv_fit);   % normalizar → distribución de prob.

    %% 5b. Actualización Kuramoto cuántica
    Theta_new = Theta;
    for i = 1:QHW.Npop
        for k = 1:Ndim
            % Acoplamiento ponderado (interferencia constructiva/destructiva)
            coupling = 0;
            for j = 1:QHW.Npop
                if j ~= i
                    % sin(θ_j - θ_i): fase relativa → dirección del ajuste
                    coupling = coupling + weights(j) * sin(Theta(j,k) - Theta(i,k));
                end
            end
            % Rotación cuántica = acoplamiento + ruido exploratorio
            delta_theta = QHW.eta * coupling + sigma_t * randn();

            % Actualizar ángulo (reflejo en límites [0, π/2])
            theta_new_ik = Theta(i,k) + delta_theta;
            theta_new_ik = mod(theta_new_ik, pi/2);  % wrap en [0, π/2]
            Theta_new(i,k) = theta_new_ik;
        end
    end

    %% 5c. Colapso cuántico: decodificar y evaluar
    Params_new = decode_theta(Theta_new, BOUNDS);
    Fitness_new = zeros(QHW.Npop, 1);
    for i = 1:QHW.Npop
        Fitness_new(i) = fitness_fn(Params_new(i,:));
    end

    %% 5d. Selección greedy (retener si mejora)
    improved = Fitness_new < Fitness;
    Theta(improved, :)  = Theta_new(improved, :);
    Params(improved, :) = Params_new(improved, :);
    Fitness(improved)   = Fitness_new(improved);

    %% 5e. Actualizar mejor global
    [cur_best, cur_idx] = min(Fitness);
    if cur_best < best_fit
        best_fit    = cur_best;
        best_params = Params(cur_idx, :);
        best_theta  = Theta(cur_idx, :);
    end

    %% 5f. Enfriar ruido (explotación creciente)
    sigma_t = max(QHW.sigma_min, sigma_t * QHW.alpha_decay);

    history_best(t) = best_fit;
    history_mean(t) = mean(Fitness);

    %% Log cada 10 iteraciones
    if mod(t,10)==0 || t==1
        rho_v   = best_params(1);
        ain_v   = best_params(2);
        lk_v    = best_params(3);
        lb_v    = best_params(4);
        fprintf('%-6d %-12.6f %-12.6f %-10.4f %-10.4f %-10.4f %-10.4f\n', ...
                t, best_fit, mean(Fitness), rho_v, ain_v, lk_v, lb_v);
    end
end

%% ─── 6. EVALUACIÓN FINAL EN TEST ────────────────────────────────────────────
fprintf('\n=== MEJOR SOLUCIÓN ENCONTRADA ===\n');
fprintf('  Radio espectral   ρ  = %.4f\n', best_params(1));
fprintf('  Escala entrada    α  = %.4f\n', best_params(2));
fprintf('  Tasa de fuga      λ  = %.4f\n', best_params(3));
fprintf('  Regularización    β  = 10^%.2f = %.2e\n', best_params(4), 10^best_params(4));

% Entrenar ESN con todos los datos train+val, evaluar en test
[Y_pred_test, rmse_test, nrmse_test] = esn_evaluate_test( ...
    best_params, W_res, W_in_base, ...
    [X_train; X_val], [Y_train; Y_val], X_test, Y_test, BOUNDS);

fprintf('\nRMSE  (test) = %.6f\n', rmse_test);
fprintf('NRMSE (test) = %.6f\n',  nrmse_test);

%% ─── 7. VISUALIZACIÓN ───────────────────────────────────────────────────────
figure('Name','Q-HW ESN — Mackey-Glass','NumberTitle','off','Position',[50 50 1400 900]);

% 7.1 Serie completa
subplot(3,3,[1 2 3]);
t_ax = 1:Ntotal;
plot(t_ax(1:n_train), Y_all(1:n_train), 'b', 'LineWidth',0.8); hold on;
plot(t_ax(n_train+1:n_train+n_val), Y_all(n_train+1:n_train+n_val), 'g','LineWidth',0.8);
plot(t_ax(n_train+n_val+1:end), Y_test, 'k','LineWidth',1.2);
xline(n_train, '--r','Train/Val','LabelVerticalAlignment','top');
xline(n_train+n_val,'--m','Val/Test','LabelVerticalAlignment','top');
title('Serie Mackey-Glass normalizada (H=1 paso adelante)');
legend('Train','Val','Test','Location','best');
xlabel('t'); ylabel('x(t)'); grid on;

% 7.2 Convergencia Q-HW
subplot(3,3,4);
plot(1:QHW.Tmax, history_best, 'r-','LineWidth',2); hold on;
plot(1:QHW.Tmax, history_mean, 'b--','LineWidth',1.2);
xlabel('Iteración'); ylabel('RMSE (val)');
title('Convergencia Q-HW');
legend('Mejor','Media pop.'); grid on;

% 7.3 Predicción vs real (test)
subplot(3,3,[5 6]);
t_test = 1:n_test;
plot(t_test, Y_test, 'k','LineWidth',1.2); hold on;
plot(t_test, Y_pred_test, 'r--','LineWidth',1.2);
title(sprintf('Test — RMSE=%.5f | NRMSE=%.5f', rmse_test, nrmse_test));
legend('Real','Q-HW ESN pred.'); xlabel('t'); ylabel('x(t)'); grid on;

% 7.4 Scatter real vs pred
subplot(3,3,7);
scatter(Y_test, Y_pred_test, 15, 'filled', 'MarkerFaceAlpha',0.5);
hold on; lims = [min(Y_test) max(Y_test)];
plot(lims, lims, 'r--','LineWidth',1.5);
xlabel('Real'); ylabel('Predicho'); title('Scatter test'); grid on;
axis equal;

% 7.5 Error absoluto
subplot(3,3,8);
plot(t_test, abs(Y_test - Y_pred_test), 'Color',[0.8 0.3 0]);
xlabel('t'); ylabel('|error|'); title('Error absoluto (test)'); grid on;

% 7.6 Parámetros óptimos
subplot(3,3,9);
bar([best_params(1:3), best_params(4)/6+0.5]);  % normalizado para visualizar
set(gca,'XTickLabel',{'\rho','\alpha','\lambda','log\beta*'});
title('Parámetros ESN óptimos (Q-HW)');
ylabel('Valor'); grid on;
text(1:4, [best_params(1:3)', best_params(4)/6+0.5]+0.02, ...
     {sprintf('%.3f',best_params(1)), sprintf('%.3f',best_params(2)), ...
      sprintf('%.3f',best_params(3)), sprintf('%.1f',best_params(4))}, ...
     'HorizontalAlignment','center','FontSize',9);

sgtitle(sprintf('Q-HW + ESN — Mackey-Glass  |  Test NRMSE = %.5f', nrmse_test), ...
        'FontSize',14, 'FontWeight','bold');

%% ─── 8. ANÁLISIS ESPECTRO DE FASES (Diagrama de Kuramoto) ──────────────────
figure('Name','Q-HW — Diagrama de Fases Final','NumberTitle','off');
theta_final = Theta;  % ángulos de la población al terminar
for k = 1:Ndim
    subplot(2,2,k);
    theta_k = theta_final(:,k);
    polarplot(theta_k, ones(size(theta_k)) * 0.9, 'o', 'MarkerSize',8, ...
              'MarkerFaceColor',[0.2 0.5 0.9]); hold on;
    polarplot(best_theta(k), 0.9, 'r*', 'MarkerSize',14, 'LineWidth',2);
    pnames = {'ρ (radio espectral)', 'α (escala entrada)', ...
              'λ (tasa de fuga)', 'log_{10}(β)'};
    title(pnames{k});
end
sgtitle('Distribución de fases cuánticas — población final Q-HW', ...
        'FontSize',12,'FontWeight','bold');

fprintf('\nListo. Figuras generadas.\n');

%% ═══════════════════════════════════════════════════════════════════════════
%%  SUBFUNCIONES
%% ═══════════════════════════════════════════════════════════════════════════

function ts = mackey_glass_gen(N, tau, beta, gamma, n, dt)
%MACKEY_GLASS_GEN  Integra la ecuación de Mackey-Glass por Euler.
%   dx/dt = beta·x(t-tau)/(1+x(t-tau)^n) - gamma·x(t)
    ts = zeros(N + tau, 1);
    ts(1:tau) = 0.9;   % condición inicial estándar
    for t = tau+1 : N+tau
        x_tau = ts(t - tau);
        ts(t) = ts(t-1) + dt * (beta * x_tau / (1 + x_tau^n) - gamma * ts(t-1));
    end
    ts = ts(tau+1:end);
end

% ─────────────────────────────────────────────────────────────────────────────

function [W_res, W_in_base] = build_reservoir(Nr, density)
%BUILD_RESERVOIR  Genera W_res (normalizada a ρ=1) y W_in_base (sin escalar).
    % Matriz de reservorio dispersa
    W = (rand(Nr,Nr) < density) .* (randn(Nr,Nr));
    ev = abs(eig(W));
    W_res = W / max(ev);   % radio espectral = 1 (se escala después)

    % Pesos de entrada base (sin escala de entrada)
    W_in_base = randn(Nr, 1);
end

% ─────────────────────────────────────────────────────────────────────────────

function Params = decode_theta(Theta, BOUNDS)
%DECODE_THETA  Mapea ángulos θ ∈ [0,π/2] a parámetros reales.
%   p_i^k = p_min^k + (p_max^k - p_min^k) · sin²(θ_i^k)
    sin2 = sin(Theta).^2;
    p_min = BOUNDS(:,1)';  % fila
    p_max = BOUNDS(:,2)';
    Params = sin2 .* (p_max - p_min) + p_min;
end

% ─────────────────────────────────────────────────────────────────────────────

function rmse_val = esn_fitness(params, W_res, W_in_base, ...
                                 X_train, Y_train, X_val, Y_val, BOUNDS)
%ESN_FITNESS  Entrena ESN con X_train/Y_train, devuelve RMSE en validación.
    rho     = params(1);
    alpha_in= params(2);
    lambda  = params(3);
    beta_reg= 10^params(4);

    Nr = size(W_res, 1);
    W  = W_res * rho;          % escalar radio espectral
    Win = W_in_base * alpha_in; % escalar entrada

    % Colectar estados del reservorio (train)
    n_tr = length(X_train);
    H_mat = zeros(n_tr, Nr);
    x = zeros(Nr, 1);
    for t = 1:n_tr
        u = X_train(t);
        x = (1-lambda)*x + lambda * tanh(W*x + Win*u);
        H_mat(t,:) = x';
    end

    % Ridge regression: Wout = (H'H + β·I)^{-1} H'Y
    Wout = (H_mat' * H_mat + beta_reg * eye(Nr)) \ (H_mat' * Y_train);

    % Evaluar en validación
    n_val = length(X_val);
    Y_pred_val = zeros(n_val, 1);
    for t = 1:n_val
        u = X_val(t);
        x = (1-lambda)*x + lambda * tanh(W*x + Win*u);
        Y_pred_val(t) = Wout' * x;
    end

    rmse_val = sqrt(mean((Y_val - Y_pred_val).^2));

    % Penalizar NaN/Inf (inestabilidad del reservorio)
    if ~isfinite(rmse_val)
        rmse_val = 1e6;
    end
end

% ─────────────────────────────────────────────────────────────────────────────

function [Y_pred, rmse, nrmse] = esn_evaluate_test( ...
        params, W_res, W_in_base, X_trainval, Y_trainval, X_test, Y_test, BOUNDS)
%ESN_EVALUATE_TEST  Re-entrena con train+val, evalúa en test.
    rho     = params(1);
    alpha_in= params(2);
    lambda  = params(3);
    beta_reg= 10^params(4);

    Nr = size(W_res, 1);
    W  = W_res * rho;
    Win = W_in_base * alpha_in;

    % Train+val
    n_tv = length(X_trainval);
    H_mat = zeros(n_tv, Nr);
    x = zeros(Nr, 1);
    for t = 1:n_tv
        u = X_trainval(t);
        x = (1-lambda)*x + lambda * tanh(W*x + Win*u);
        H_mat(t,:) = x';
    end
    Wout = (H_mat' * H_mat + beta_reg * eye(Nr)) \ (H_mat' * Y_trainval);

    % Test
    n_te = length(X_test);
    Y_pred = zeros(n_te, 1);
    for t = 1:n_te
        u = X_test(t);
        x = (1-lambda)*x + lambda * tanh(W*x + Win*u);
        Y_pred(t) = Wout' * x;
    end

    rmse  = sqrt(mean((Y_test - Y_pred).^2));
    nrmse = rmse / std(Y_test);
end
