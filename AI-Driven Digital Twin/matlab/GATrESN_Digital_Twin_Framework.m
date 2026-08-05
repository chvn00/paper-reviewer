%% GATrESN Digital Twin Framework
% Reproducible simulation-based case study for strategic operations management.
% The model uses:
% 1. Synthetic multi-site operational data generation.
% 2. Echo State Network reservoir embeddings for nonlinear temporal memory.
% 3. Transformer-style self-attention over lagged reservoir states.
% 4. Ridge-regression readout for reproducible forecasting.
% 5. Genetic Algorithm optimizer for multi-lever strategic policy selection.
%
% GATrESN = Genetic Algorithm + Transformer-style attention + Echo State Network.

clear; clc; close all;
rng(2026, 'twister');

%% Paths
rootDir = fileparts(fileparts(mfilename('fullpath')));
dataDir = fullfile(rootDir, 'data');
resultsDir = fullfile(rootDir, 'results');
figuresDir = fullfile(rootDir, 'figures');

if ~exist(dataDir, 'dir'), mkdir(dataDir); end
if ~exist(resultsDir, 'dir'), mkdir(resultsDir); end
if ~exist(figuresDir, 'dir'), mkdir(figuresDir); end

writeCaseStudyContext(resultsDir);

%% Study scale
runMode = "paper"; % Options: "quick", "paper", "stress"

switch runMode
    case "quick"
        nSites = 8;
        nProducts = 6;
        nPeriods = 240;
        maxDecisionRows = 120;
        gaPopulation = 60;
        gaGenerations = 80;
        monteCarloScenarios = 5;
        esnReservoirSize = 180;
        attentionHeads = 6;
    case "paper"
        nSites = 24;
        nProducts = 16;
        nPeriods = 640;
        maxDecisionRows = 1800;
        gaPopulation = 140;
        gaGenerations = 180;
        monteCarloScenarios = 35;
        esnReservoirSize = 240;
        attentionHeads = 8;
    case "stress"
        nSites = 36;
        nProducts = 24;
        nPeriods = 840;
        maxDecisionRows = 4200;
        gaPopulation = 220;
        gaGenerations = 280;
        monteCarloScenarios = 60;
        esnReservoirSize = 320;
        attentionHeads = 8;
    otherwise
        error('Unknown runMode. Use "quick", "paper", or "stress".');
end
nLags = 12;
horizon = 1;

config = struct();
config.seed = 2026;
config.runMode = runMode;
config.nSites = nSites;
config.nProducts = nProducts;
config.nPeriods = nPeriods;
config.nLags = nLags;
config.horizon = horizon;
config.maxDecisionRows = maxDecisionRows;
config.monteCarloScenarios = monteCarloScenarios;
config.esnReservoirSize = esnReservoirSize;
config.esnSpectralRadius = 0.92;
config.esnLeakRate = 0.35;
config.esnInputScale = 0.45;
config.attentionHeads = attentionHeads;
config.ridgeLambda = 1e-2;
config.gaPopulation = gaPopulation;
config.gaGenerations = gaGenerations;
config.gaMutationRate = 0.12;
config.parallelWorkers = 12;

fprintf('\nGATrESN case study: enterprise-scale strategic operations network.\n');
fprintf('Run mode: %s\n', runMode);
fprintf('Scope: %d sites, %d product families, %d planning periods.\n', ...
    nSites, nProducts, nPeriods);
fprintf('Decision instances: up to %d; GA population: %d; GA generations: %d; Monte Carlo scenarios: %d.\n', ...
    maxDecisionRows, gaPopulation, gaGenerations, monteCarloScenarios);
fprintf('Outputs will be written to:\n  %s\n  %s\n  %s\n\n', dataDir, resultsDir, figuresDir);

useParallel = startParallelPool(config.parallelWorkers);
config.useParallel = useParallel;

save(fullfile(resultsDir, 'GATrESN_model_config.mat'), 'config');

%% Generate synthetic enterprise-scale operations data
ops = generateOperationsData(nSites, nProducts, nPeriods);
writetable(ops, fullfile(dataDir, 'synthetic_enterprise_operations_data.csv'));

%% Feature engineering
[X, Y, meta] = buildSupervisedDataset(ops, nLags, horizon);
nObs = size(X, 1);
trainEnd = floor(0.70 * nObs);
valEnd = floor(0.85 * nObs);

XTrain = X(1:trainEnd, :);
YTrain = Y(1:trainEnd, :);
XVal = X(trainEnd+1:valEnd, :);
YVal = Y(trainEnd+1:valEnd, :);
XTest = X(valEnd+1:end, :);
YTest = Y(valEnd+1:end, :);
metaTest = meta(valEnd+1:end, :);

%% ESN reservoir embeddings
esn = initializeESN(size(XTrain, 2), config.esnReservoirSize, ...
    config.esnSpectralRadius, config.esnInputScale, config.esnLeakRate);

ZTrain = computeESNStates(esn, XTrain);
ZVal = computeESNStates(esn, XVal);
ZTest = computeESNStates(esn, XTest);

%% Transformer-style attention over reservoir states
Atrain = attentionFeatures(ZTrain, nLags, config.attentionHeads);
Aval = attentionFeatures(ZVal, nLags, config.attentionHeads);
Atest = attentionFeatures(ZTest, nLags, config.attentionHeads);

PhiTrain = [ones(size(Atrain, 1), 1), XTrain, ZTrain, Atrain];
PhiVal = [ones(size(Aval, 1), 1), XVal, ZVal, Aval];
PhiTest = [ones(size(Atest, 1), 1), XTest, ZTest, Atest];

%% Reproducible ridge readout
lambda = config.ridgeLambda;
Wout = (PhiTrain' * PhiTrain + lambda * eye(size(PhiTrain, 2))) \ (PhiTrain' * YTrain);

YHatTrain = PhiTrain * Wout;
YHatVal = PhiVal * Wout;
YHatTest = PhiTest * Wout;

metrics = table( ...
    ["Train"; "Validation"; "Test"], ...
    [rmse(YTrain, YHatTrain); rmse(YVal, YHatVal); rmse(YTest, YHatTest)], ...
    [mae(YTrain, YHatTrain); mae(YVal, YHatVal); mae(YTest, YHatTest)], ...
    'VariableNames', {'Split', 'RMSE', 'MAE'});

writetable(metrics, fullfile(resultsDir, 'GATrESN_forecasting_metrics.csv'));
disp(metrics);

%% Strategic digital twin with GA decision optimization
testRows = min(config.maxDecisionRows, size(YHatTest, 1));

Site = zeros(testRows, 1);
Product = zeros(testRows, 1);
Period = zeros(testRows, 1);
ForecastDemand = zeros(testRows, 1);
ForecastRisk = zeros(testRows, 1);
CapacityMultiplier = zeros(testRows, 1);
CostMultiplier = zeros(testRows, 1);
ResilienceInvestment = zeros(testRows, 1);
InventoryBuffer = zeros(testRows, 1);
WorkforceFlexibility = zeros(testRows, 1);
SupplierRedundancy = zeros(testRows, 1);
OptimizedCapacity = zeros(testRows, 1);
ServiceLevel = zeros(testRows, 1);
Utilization = zeros(testRows, 1);
ExpectedCost = zeros(testRows, 1);
ResidualRisk = zeros(testRows, 1);
StrategicScore = zeros(testRows, 1);

if useParallel
    parfor i = 1:testRows
        [Site(i), Product(i), Period(i), ForecastDemand(i), ForecastRisk(i), ...
            CapacityMultiplier(i), CostMultiplier(i), ResilienceInvestment(i), ...
            InventoryBuffer(i), WorkforceFlexibility(i), SupplierRedundancy(i), ...
            OptimizedCapacity(i), ServiceLevel(i), Utilization(i), ExpectedCost(i), ...
            ResidualRisk(i), StrategicScore(i)] = optimizeDecisionInstance( ...
            i, YHatTest, metaTest, config);
    end
else
    for i = 1:testRows
        [Site(i), Product(i), Period(i), ForecastDemand(i), ForecastRisk(i), ...
            CapacityMultiplier(i), CostMultiplier(i), ResilienceInvestment(i), ...
            InventoryBuffer(i), WorkforceFlexibility(i), SupplierRedundancy(i), ...
            OptimizedCapacity(i), ServiceLevel(i), Utilization(i), ExpectedCost(i), ...
            ResidualRisk(i), StrategicScore(i)] = optimizeDecisionInstance( ...
            i, YHatTest, metaTest, config);
    end
end

decisionResults = table(Site, Product, Period, ForecastDemand, ForecastRisk, ...
    CapacityMultiplier, CostMultiplier, ResilienceInvestment, InventoryBuffer, ...
    WorkforceFlexibility, SupplierRedundancy, OptimizedCapacity, ...
    ServiceLevel, Utilization, ExpectedCost, ResidualRisk, StrategicScore);

writetable(decisionResults, fullfile(resultsDir, 'GATrESN_ga_decision_results.csv'));

decisionSummary = table( ...
    mean(decisionResults.ForecastDemand), ...
    mean(decisionResults.ServiceLevel), ...
    mean(decisionResults.Utilization), ...
    mean(decisionResults.ExpectedCost), ...
    mean(decisionResults.ResidualRisk), ...
    mean(decisionResults.StrategicScore), ...
    'VariableNames', {'MeanForecastDemand', 'MeanServiceLevel', 'MeanUtilization', ...
    'MeanExpectedCost', 'MeanResidualRisk', 'MeanStrategicScore'});
writetable(decisionSummary, fullfile(resultsDir, 'GATrESN_decision_summary.csv'));

%% Benchmark comparison against alternative decision models
[benchmarkResults, benchmarkSummary] = buildBenchmarkComparison(decisionResults, YHatTest, metaTest, testRows);
writetable(benchmarkResults, fullfile(resultsDir, 'GATrESN_benchmark_comparison.csv'));
writetable(benchmarkSummary, fullfile(resultsDir, 'GATrESN_benchmark_summary.csv'));
statisticalValidation = buildStatisticalValidation(benchmarkResults);
writetable(statisticalValidation, fullfile(resultsDir, 'GATrESN_statistical_validation.csv'));

manifest = {
    'GATrESN reproducibility manifest'
    ['Seed: ' num2str(config.seed)]
    ['Run mode: ' char(config.runMode)]
    ['Sites: ' num2str(config.nSites)]
    ['Products: ' num2str(config.nProducts)]
    ['Periods: ' num2str(config.nPeriods)]
    ['Decision instances evaluated: ' num2str(testRows)]
    ['Monte Carlo scenarios per decision: ' num2str(config.monteCarloScenarios)]
    ['Lags: ' num2str(config.nLags)]
    ['ESN reservoir size: ' num2str(config.esnReservoirSize)]
    ['ESN spectral radius: ' num2str(config.esnSpectralRadius)]
    ['Attention heads: ' num2str(config.attentionHeads)]
    ['GA population: ' num2str(config.gaPopulation)]
    ['GA generations: ' num2str(config.gaGenerations)]
    'Strategic decision variables: capacity multiplier, cost-policy multiplier, resilience investment, inventory buffer, workforce flexibility, supplier redundancy'
    ['Parallel execution enabled: ' logicalText(config.useParallel)]
    ['Requested parallel workers: ' num2str(config.parallelWorkers)]
    'Generated files:'
    'data/synthetic_enterprise_operations_data.csv'
    'results/GATrESN_forecasting_metrics.csv'
    'results/GATrESN_ga_decision_results.csv'
    'results/GATrESN_decision_summary.csv'
    'results/GATrESN_benchmark_comparison.csv'
    'results/GATrESN_benchmark_summary.csv'
    'results/GATrESN_statistical_validation.csv'
    'results/GATrESN_case_study_context.txt'
    'figures/GATrESN_demand_forecast.png'
    'figures/GATrESN_strategic_score.png'
    'figures/GATrESN_service_level.png'
    'figures/GATrESN_residual_risk.png'
    'figures/GATrESN_data_organization.png'
    'figures/GATrESN_benchmark_strategic_score.png'
    'figures/GATrESN_benchmark_kpi_dashboard.png'
    'figures/GATrESN_benchmark_distribution_analysis.png'
    'figures/GATrESN_cost_risk_tradeoff.png'
};
writecell(manifest, fullfile(resultsDir, 'GATrESN_reproducibility_manifest.txt'), ...
    'FileType', 'text');

%% Figures
plotDataOrganization(config, testRows, height(data), height(benchmarkResults), ...
    fullfile(figuresDir, 'GATrESN_data_organization.png'));
plotForecast(YTest(1:testRows, 1), YHatTest(1:testRows, 1), ...
    fullfile(figuresDir, 'GATrESN_demand_forecast.png'));
plotDecisionSeries(decisionResults, 'StrategicScore', ...
    'GATrESN-Optimized Strategic Score', fullfile(figuresDir, 'GATrESN_strategic_score.png'));
plotDecisionSeries(decisionResults, 'ServiceLevel', ...
    'GATrESN-Optimized Service Level', fullfile(figuresDir, 'GATrESN_service_level.png'));
plotDecisionSeries(decisionResults, 'ResidualRisk', ...
    'GATrESN-Optimized Residual Risk', fullfile(figuresDir, 'GATrESN_residual_risk.png'));
plotBenchmarkSummary(benchmarkSummary, ...
    fullfile(figuresDir, 'GATrESN_benchmark_strategic_score.png'));
plotBenchmarkKpiDashboard(benchmarkSummary, ...
    fullfile(figuresDir, 'GATrESN_benchmark_kpi_dashboard.png'));
plotBenchmarkDistributions(benchmarkResults, ...
    fullfile(figuresDir, 'GATrESN_benchmark_distribution_analysis.png'));
plotCostRiskTradeoff(benchmarkResults, benchmarkSummary, ...
    fullfile(figuresDir, 'GATrESN_cost_risk_tradeoff.png'));

%% Local functions
function [benchmarkResults, benchmarkSummary] = buildBenchmarkComparison(decisionResults, YHatTest, metaTest, testRows)
    benchmarkResults = table();

    for i = 1:testRows
        forecastDemand = max(YHatTest(i, 1), 1);
        forecastRisk = min(max(YHatTest(i, 2), 0), 1);
        site = metaTest.Site(i);
        product = metaTest.Product(i);
        period = metaTest.Period(i);
        baseCapacity = metaTest.BaseCapacity(i);
        baseUnitCost = metaTest.UnitCost(i);

        gatrDecision = [
            decisionResults.CapacityMultiplier(i), ...
            decisionResults.CostMultiplier(i), ...
            decisionResults.ResilienceInvestment(i), ...
            decisionResults.InventoryBuffer(i), ...
            decisionResults.WorkforceFlexibility(i), ...
            decisionResults.SupplierRedundancy(i)
        ];
        lpDecision = linearProgrammingPolicy(forecastDemand, forecastRisk, baseCapacity, baseUnitCost);
        ruleDecision = ruleBasedPolicy(forecastDemand, forecastRisk, baseCapacity);

        benchmarkResults = [benchmarkResults; makeBenchmarkRow("GATrESN", site, product, period, ...
            forecastDemand, forecastRisk, baseCapacity, baseUnitCost, gatrDecision)]; %#ok<AGROW>
        benchmarkResults = [benchmarkResults; makeBenchmarkRow("LP-Simplified", site, product, period, ...
            forecastDemand, forecastRisk, baseCapacity, baseUnitCost, lpDecision)]; %#ok<AGROW>
        benchmarkResults = [benchmarkResults; makeBenchmarkRow("Rule-Based", site, product, period, ...
            forecastDemand, forecastRisk, baseCapacity, baseUnitCost, ruleDecision)]; %#ok<AGROW>
    end

    models = unique(benchmarkResults.Model, 'stable');
    benchmarkSummary = table();
    for m = 1:numel(models)
        idx = benchmarkResults.Model == models(m);
        row = table(models(m), ...
            mean(benchmarkResults.ServiceLevel(idx)), ...
            mean(benchmarkResults.Utilization(idx)), ...
            mean(benchmarkResults.ExpectedCost(idx)), ...
            mean(benchmarkResults.ResidualRisk(idx)), ...
            mean(benchmarkResults.StrategicScore(idx)), ...
            'VariableNames', {'Model', 'MeanServiceLevel', 'MeanUtilization', ...
            'MeanExpectedCost', 'MeanResidualRisk', 'MeanStrategicScore'});
        benchmarkSummary = [benchmarkSummary; row]; %#ok<AGROW>
    end
    benchmarkSummary = sortrows(benchmarkSummary, 'MeanStrategicScore', 'descend');
end

function validationTable = buildStatisticalValidation(benchmarkResults)
    metrics = ["StrategicScore", "ServiceLevel", "ResidualRisk"];
    directions = ["higher", "higher", "lower"];
    benchmarks = ["Rule-Based", "LP-Simplified"];
    nComparisons = numel(metrics) * numel(benchmarks);

    Metric = strings(nComparisons, 1);
    Comparison = strings(nComparisons, 1);
    N = zeros(nComparisons, 1);
    MeanAdvantage = zeros(nComparisons, 1);
    MedianAdvantage = zeros(nComparisons, 1);
    BootstrapCI95Lower = zeros(nComparisons, 1);
    BootstrapCI95Upper = zeros(nComparisons, 1);
    DominanceRate = zeros(nComparisons, 1);
    SignTestPValue = zeros(nComparisons, 1);
    CohenDz = zeros(nComparisons, 1);

    rng(20260621);
    rowIdx = 0;
    for k = 1:numel(metrics)
        gatrValues = benchmarkResults{benchmarkResults.Model == "GATrESN", metrics(k)};
        for b = 1:numel(benchmarks)
            rowIdx = rowIdx + 1;
            benchmarkValues = benchmarkResults{benchmarkResults.Model == benchmarks(b), metrics(k)};
            if directions(k) == "higher"
                pairedAdvantage = gatrValues - benchmarkValues;
            else
                pairedAdvantage = benchmarkValues - gatrValues;
            end

            ci = bootstrapMeanCI(pairedAdvantage, 2000);
            wins = sum(pairedAdvantage > 0);
            losses = sum(pairedAdvantage < 0);
            nNonTie = wins + losses;
            z = (abs(wins - nNonTie / 2) - 0.5) / sqrt(nNonTie / 4);
            pValue = erfc(z / sqrt(2));

            Metric(rowIdx) = metrics(k);
            Comparison(rowIdx) = "GATrESN vs " + benchmarks(b);
            N(rowIdx) = numel(pairedAdvantage);
            MeanAdvantage(rowIdx) = mean(pairedAdvantage);
            MedianAdvantage(rowIdx) = median(pairedAdvantage);
            BootstrapCI95Lower(rowIdx) = ci(1);
            BootstrapCI95Upper(rowIdx) = ci(2);
            DominanceRate(rowIdx) = wins / numel(pairedAdvantage);
            SignTestPValue(rowIdx) = pValue;
            CohenDz(rowIdx) = mean(pairedAdvantage) / std(pairedAdvantage);
        end
    end

    SignTestPValueHolm = holmAdjust(SignTestPValue);
    validationTable = table(Metric, Comparison, N, MeanAdvantage, MedianAdvantage, ...
        BootstrapCI95Lower, BootstrapCI95Upper, DominanceRate, ...
        SignTestPValueHolm, CohenDz);
end

function ci = bootstrapMeanCI(values, nBoot)
    n = numel(values);
    bootMeans = zeros(nBoot, 1);
    for b = 1:nBoot
        idx = randi(n, n, 1);
        bootMeans(b) = mean(values(idx));
    end
    bootMeans = sort(bootMeans);
    lowerIdx = max(1, round(0.025 * nBoot));
    upperIdx = min(nBoot, round(0.975 * nBoot));
    ci = [bootMeans(lowerIdx), bootMeans(upperIdx)];
end

function adjustedP = holmAdjust(rawP)
    m = numel(rawP);
    adjustedP = zeros(size(rawP));
    [~, order] = sort(rawP);
    cumulative = 0;
    for r = 1:m
        idx = order(r);
        value = min(1, rawP(idx) * (m - r + 1));
        cumulative = max(cumulative, value);
        adjustedP(idx) = cumulative;
    end
end

function row = makeBenchmarkRow(modelName, site, product, period, forecastDemand, ...
    forecastRisk, baseCapacity, baseUnitCost, decision)

    decision = completeDecisionVector(decision);
    capacityMultiplier = decision(1);
    costMultiplier = decision(2);
    resilienceInvestment = decision(3);
    inventoryBuffer = decision(4);
    workforceFlexibility = decision(5);
    supplierRedundancy = decision(6);
    [optimizedCapacity, serviceLevel, utilization, expectedCost, residualRisk, strategicScore] = ...
        evaluateStrategicDecision(decision, forecastDemand, forecastRisk, baseCapacity, baseUnitCost);

    row = table(modelName, site, product, period, forecastDemand, forecastRisk, ...
        capacityMultiplier, costMultiplier, resilienceInvestment, inventoryBuffer, ...
        workforceFlexibility, supplierRedundancy, optimizedCapacity, ...
        serviceLevel, utilization, expectedCost, residualRisk, strategicScore, ...
        'VariableNames', {'Model', 'Site', 'Product', 'Period', 'ForecastDemand', ...
        'ForecastRisk', 'CapacityMultiplier', 'CostMultiplier', 'ResilienceInvestment', ...
        'InventoryBuffer', 'WorkforceFlexibility', 'SupplierRedundancy', 'OptimizedCapacity', ...
        'ServiceLevel', 'Utilization', 'ExpectedCost', 'ResidualRisk', 'StrategicScore'});
end

function decision = linearProgrammingPolicy(forecastDemand, forecastRisk, baseCapacity, baseUnitCost)
    lb = [0.80; 0.82; 0.00; 0.00; 0.00; 0.00];
    ub = [1.40; 1.28; 1.00; 1.00; 1.00; 1.00];
    targetService = 0.95;
    targetRisk = 0.18;

    f = [0.10 * baseCapacity * baseUnitCost; forecastDemand * baseUnitCost; ...
        420; 160; 280; 360];
    A = [-baseCapacity, 0, 0, -0.10 * baseCapacity, -0.08 * baseCapacity, -0.06 * baseCapacity];
    b = -targetService * forecastDemand;

    if forecastRisk > targetRisk
        A = [A; 0, 0, -0.35 * forecastRisk, -0.18 * forecastRisk, ...
            -0.20 * forecastRisk, -0.25 * forecastRisk];
        b = [b; targetRisk - forecastRisk];
    end

    if exist('linprog', 'file') == 2
        try
            options = optimoptions('linprog', 'Display', 'none');
            [x, ~, exitflag] = linprog(f, A, b, [], [], lb, ub, options);
            if exitflag > 0
                decision = x';
                return;
            end
        catch
        end
    end

    capacityMultiplier = min(max(targetService * forecastDemand / baseCapacity, lb(1)), ub(1));
    if forecastRisk > targetRisk
        resilienceInvestment = min(max(0.55 * (forecastRisk - targetRisk) / max(0.35 * forecastRisk, 1e-6), lb(3)), ub(3));
        inventoryBuffer = min(max(0.25 * (forecastRisk - targetRisk) / max(forecastRisk, 1e-6), lb(4)), ub(4));
        workforceFlexibility = min(max(0.20 * forecastDemand / max(baseCapacity, 1) - 0.12, lb(5)), ub(5));
        supplierRedundancy = min(max(0.35 * (forecastRisk - targetRisk) / max(forecastRisk, 1e-6), lb(6)), ub(6));
    else
        resilienceInvestment = 0;
        inventoryBuffer = 0.05;
        workforceFlexibility = 0.05;
        supplierRedundancy = 0;
    end
    costMultiplier = lb(2);
    decision = [capacityMultiplier, costMultiplier, resilienceInvestment, ...
        inventoryBuffer, workforceFlexibility, supplierRedundancy];
end

function decision = ruleBasedPolicy(forecastDemand, forecastRisk, baseCapacity)
    pressure = forecastDemand / max(baseCapacity, 1);
    capacityMultiplier = min(max(0.92 + 0.22 * max(pressure - 0.90, 0), 0.85), 1.25);
    if forecastRisk > 0.35
        resilienceInvestment = 0.70;
        inventoryBuffer = 0.55;
        workforceFlexibility = 0.45;
        supplierRedundancy = 0.65;
        costMultiplier = 1.08;
    elseif pressure > 1.05
        resilienceInvestment = 0.35;
        inventoryBuffer = 0.40;
        workforceFlexibility = 0.35;
        supplierRedundancy = 0.25;
        costMultiplier = 1.02;
    else
        resilienceInvestment = 0.10;
        inventoryBuffer = 0.10;
        workforceFlexibility = 0.10;
        supplierRedundancy = 0.05;
        costMultiplier = 0.92;
    end
    decision = [capacityMultiplier, costMultiplier, resilienceInvestment, ...
        inventoryBuffer, workforceFlexibility, supplierRedundancy];
end

function [optimizedCapacity, serviceLevel, utilization, expectedCost, residualRisk, strategicScore] = ...
    evaluateStrategicDecision(decision, forecastDemand, forecastRisk, baseCapacity, baseUnitCost)

    decision = completeDecisionVector(decision);
    capacityMultiplier = decision(1);
    costMultiplier = decision(2);
    resilienceInvestment = decision(3);
    inventoryBuffer = decision(4);
    workforceFlexibility = decision(5);
    supplierRedundancy = decision(6);

    optimizedCapacity = baseCapacity * capacityMultiplier * (1 + 0.08 * workforceFlexibility);
    availabilityBuffer = 1 + 0.10 * inventoryBuffer + 0.06 * supplierRedundancy;
    effectiveCapacity = optimizedCapacity * availabilityBuffer;
    qualityPenalty = 1 - 0.18 * max(0, 0.95 - costMultiplier) / 0.13;
    qualityPenalty = min(max(qualityPenalty, 0.82), 1.0);
    expectedFulfillment = min(forecastDemand, effectiveCapacity) * qualityPenalty;
    serviceLevel = expectedFulfillment / forecastDemand;
    utilization = expectedFulfillment / effectiveCapacity;
    expectedCost = expectedFulfillment * baseUnitCost * costMultiplier ...
        + 420 * resilienceInvestment ...
        + 160 * inventoryBuffer ...
        + 280 * workforceFlexibility ...
        + 360 * supplierRedundancy ...
        + 0.035 * baseCapacity * baseUnitCost * max(0, capacityMultiplier - 1);
    riskMitigation = 0.35 * resilienceInvestment + 0.18 * inventoryBuffer ...
        + 0.20 * workforceFlexibility + 0.25 * supplierRedundancy;
    complexityRisk = 0.025 * max(0, capacityMultiplier - 1.15) ...
        + 0.035 * max(0, 0.92 - costMultiplier);
    residualRisk = min(max(forecastRisk * (1 - riskMitigation) + complexityRisk, 0), 1);
    strategicScore = strategicUtility(decision, forecastDemand, forecastRisk, baseCapacity, baseUnitCost);
end

function plotBenchmarkSummary(benchmarkSummary, outputPath)
    figure('Color', 'w', 'Position', [100 100 900 520]);
    bar(categorical(benchmarkSummary.Model), benchmarkSummary.MeanStrategicScore);
    grid on;
    xlabel('Decision Model');
    ylabel('Mean Strategic Score');
    title('Benchmark Comparison of Strategic Decision Models');
    exportgraphics(gcf, outputPath, 'Resolution', 300);
end

function plotBenchmarkKpiDashboard(benchmarkSummary, outputPath)
    modelOrder = ["GATrESN", "Rule-Based", "LP-Simplified"];
    metrics = ["MeanServiceLevel", "MeanUtilization", "MeanResidualRisk", "MeanStrategicScore"];
    labels = ["Service level", "Utilization", "Residual risk", "Strategic score"];
    palette = [0.1216 0.4667 0.7059; 1.0000 0.4980 0.0549; 0.1725 0.6275 0.1725];

    figure('Color', 'w', 'Position', [100 100 1320 900]);
    tiledlayout(2, 2, 'Padding', 'compact', 'TileSpacing', 'compact');
    for k = 1:numel(metrics)
        nexttile;
        values = zeros(1, numel(modelOrder));
        for m = 1:numel(modelOrder)
            values(m) = benchmarkSummary{benchmarkSummary.Model == modelOrder(m), metrics(k)};
        end
        b = bar(categorical(modelOrder), values, 'FaceColor', 'flat');
        b.CData = palette;
        grid on;
        title(labels(k));
        ylim([0 max(values) * 1.22]);
        for m = 1:numel(values)
            text(m, values(m), sprintf('%.3f', values(m)), ...
                'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom');
        end
    end
    exportgraphics(gcf, outputPath, 'Resolution', 300);
end

function plotBenchmarkDistributions(benchmarkResults, outputPath)
    modelOrder = ["GATrESN", "Rule-Based", "LP-Simplified"];
    metrics = ["StrategicScore", "ServiceLevel", "ResidualRisk", "ExpectedCost"];
    labels = ["Strategic score", "Service level", "Residual risk", "Expected cost"];
    palette = [0.1216 0.4667 0.7059; 1.0000 0.4980 0.0549; 0.1725 0.6275 0.1725];

    figure('Color', 'w', 'Position', [100 100 1320 900]);
    tiledlayout(2, 2, 'Padding', 'compact', 'TileSpacing', 'compact');
    for k = 1:numel(metrics)
        nexttile;
        hold on;
        for m = 1:numel(modelOrder)
            idx = benchmarkResults.Model == modelOrder(m);
            modelValues = benchmarkResults{idx, metrics(k)};
            groups = categorical(repmat(modelOrder(m), numel(modelValues), 1), modelOrder, 'Ordinal', true);
            boxchart(groups, modelValues, 'MarkerStyle', 'none', 'BoxFaceColor', palette(m, :));
        end
        hold off;
        grid on;
        title(labels(k));
        xlabel('');
    end
    exportgraphics(gcf, outputPath, 'Resolution', 300);
end

function plotCostRiskTradeoff(benchmarkResults, benchmarkSummary, outputPath)
    modelOrder = ["GATrESN", "Rule-Based", "LP-Simplified"];
    palette = [0.1216 0.4667 0.7059; 1.0000 0.4980 0.0549; 0.1725 0.6275 0.1725];

    figure('Color', 'w', 'Position', [100 100 1250 820]);
    hold on;
    for m = 1:numel(modelOrder)
        idx = benchmarkResults.Model == modelOrder(m);
        sampleIdx = find(idx);
        if numel(sampleIdx) > 600
            rng(42 + m);
            sampleIdx = sampleIdx(randperm(numel(sampleIdx), 600));
        end
        scatter(benchmarkResults.ExpectedCost(sampleIdx), benchmarkResults.ResidualRisk(sampleIdx), ...
            18, palette(m, :), 'filled', 'MarkerFaceAlpha', 0.55, 'DisplayName', modelOrder(m));
        meanIdx = benchmarkSummary.Model == modelOrder(m);
        scatter(benchmarkSummary.MeanExpectedCost(meanIdx), benchmarkSummary.MeanResidualRisk(meanIdx), ...
            120, palette(m, :), 'd', 'filled', 'MarkerEdgeColor', 'k', 'HandleVisibility', 'off');
    end
    grid on;
    xlabel('Expected cost');
    ylabel('Residual risk');
    title('Cost-risk trade-off across decision instances');
    legend('Location', 'northeast');
    hold off;
    exportgraphics(gcf, outputPath, 'Resolution', 300);
end

function plotDataOrganization(config, decisionRows, operationalRows, benchmarkRows, outputPath)
    figure('Color', 'w', 'Position', [100 100 1600 900]);
    ax = axes('Position', [0 0 1 1]);
    axis(ax, 'off');
    hold(ax, 'on');

    titleColor = [0.07 0.10 0.16];
    blue = [0.1216 0.4667 0.7059];
    orange = [1.0000 0.4980 0.0549];
    green = [0.1725 0.6275 0.1725];
    purple = [0.5804 0.4039 0.7412];

    text(ax, 0.5, 0.94, 'Operational Data Organization for the GATrESN Digital Twin', ...
        'HorizontalAlignment', 'center', 'FontSize', 22, 'FontWeight', 'bold', 'Color', titleColor);

    drawDataBox(ax, [0.04 0.63 0.27 0.22], blue, 'Panel structure', { ...
        sprintf('%d operational sites', config.nSites), ...
        sprintf('%d product families', config.nProducts), ...
        sprintf('%d planning periods', config.nPeriods), ...
        sprintf('%s site-product-period records', groupedNumber(operationalRows)), ...
        'No missing values'});
    drawDataBox(ax, [0.365 0.63 0.27 0.22], green, 'State variables', { ...
        'Site, Product, Period', ...
        'Demand, BaseCapacity, UnitCost', ...
        'ServicePressure, ExternalRisk', ...
        'LaborAvailability, InventoryCoverage'});
    drawDataBox(ax, [0.69 0.63 0.27 0.22], orange, 'Variable type', { ...
        'Site and Product: categorical IDs', ...
        'Period: ordered temporal index', ...
        'Seven operational indicators:', ...
        'continuous numerical variables'});

    drawArrow(ax, [0.315 0.74], [0.36 0.74]);
    drawArrow(ax, [0.64 0.74], [0.685 0.74]);

    drawDataBox(ax, [0.07 0.33 0.24 0.19], purple, 'Temporal encoding', { ...
        sprintf('Lag window length: L = %d', config.nLags), ...
        'State tensor organized by', ...
        'site, product, period, variables'});
    drawDataBox(ax, [0.38 0.33 0.24 0.19], blue, 'Digital twin state', { ...
        'Historical operational memory', ...
        'Demand-risk projection', ...
        'Scenario-ready virtual state'});
    drawDataBox(ax, [0.69 0.33 0.24 0.19], green, 'Decision dataset', { ...
        sprintf('%s matched decision states', groupedNumber(decisionRows)), ...
        'Evaluated by 3 models', ...
        sprintf('%s benchmark rows', groupedNumber(benchmarkRows))});

    drawArrow(ax, [0.315 0.425], [0.375 0.425]);
    drawArrow(ax, [0.625 0.425], [0.685 0.425]);

    text(ax, 0.5, 0.24, 'Common KPI layer used for GATrESN, Rule-Based, and LP-Simplified validation', ...
        'HorizontalAlignment', 'center', 'FontSize', 15, 'FontWeight', 'bold', 'Color', titleColor);
    kpiNames = {'Service level', 'Utilization', 'Expected cost', 'Residual risk', 'Strategic score'};
    kpiColors = [blue; orange; green; purple; 0.8392 0.1529 0.1569];
    for k = 1:numel(kpiNames)
        x = 0.065 + (k - 1) * 0.185;
        rectangle(ax, 'Position', [x 0.115 0.15 0.075], 'Curvature', 0.18, ...
            'FaceColor', 'w', 'EdgeColor', kpiColors(k, :), 'LineWidth', 2.5);
        text(ax, x + 0.075, 0.152, kpiNames{k}, 'HorizontalAlignment', 'center', ...
            'FontSize', 12.5, 'FontWeight', 'bold', 'Color', titleColor);
    end
    text(ax, 0.5, 0.055, ...
        'The data organization supports temporal forecasting, scenario simulation, paired benchmark comparison, and statistical validation.', ...
        'HorizontalAlignment', 'center', 'FontSize', 12, 'Color', [0.22 0.26 0.32]);
    hold(ax, 'off');
    exportgraphics(gcf, outputPath, 'Resolution', 300);
end

function drawDataBox(ax, pos, color, titleText, lines)
    fillColor = 0.88 * ones(1, 3) + 0.12 * color;
    rectangle(ax, 'Position', pos, 'Curvature', 0.08, 'FaceColor', fillColor, ...
        'EdgeColor', color, 'LineWidth', 2.4);
    text(ax, pos(1) + 0.018, pos(2) + pos(4) - 0.045, titleText, ...
        'FontSize', 15, 'FontWeight', 'bold', 'Color', color);
    for j = 1:numel(lines)
        text(ax, pos(1) + 0.022, pos(2) + pos(4) - 0.082 - 0.03 * j, lines{j}, ...
            'FontSize', 11.5, 'Color', [0.07 0.10 0.16]);
    end
end

function drawArrow(ax, p1, p2)
    annotation(gcf, 'arrow', [p1(1) p2(1)], [p1(2) p2(2)], ...
        'Color', [0.20 0.23 0.27], 'LineWidth', 2.4, 'HeadLength', 10, 'HeadWidth', 10);
end

function txt = groupedNumber(value)
    raw = sprintf('%d', value);
    txt = raw;
    insertAt = strlength(txt) - 2;
    while insertAt > 1
        txt = [char(extractBefore(txt, insertAt)), ',', char(extractAfter(txt, insertAt - 1))];
        insertAt = insertAt - 3;
    end
    txt = char(txt);
end

function writeCaseStudyContext(resultsDir)
    context = {
        'GATrESN case study context'
        ''
        'Case name: Strategic Operations Network for AI-driven digital twin evaluation.'
        ''
        'The case represents a distributed enterprise operations system composed of multiple operational sites and multiple product families. It is designed to evaluate strategic operations management decisions under uncertainty, rather than a single machine, isolated production line, or simple forecasting problem.'
        ''
        'Operational scale:'
        '- 24 operational sites, 16 product families, and 640 sequential planning periods.'
        '- 245,760 site-product-period operational records before lag construction.'
        '- 1,800 matched strategic decision states are evaluated in the benchmark analysis.'
        '- Monte Carlo stress evaluation is embedded inside each strategic decision instance.'
        '- Generated records are transformed into supervised lagged temporal states for ESN-attention modeling.'
        '- Persistent disruption states create temporal dependencies across demand, capacity, labor, inventory, cost, and risk.'
        ''
        'Operational indicators:'
        '- Demand.'
        '- Base capacity.'
        '- Unit cost.'
        '- Service pressure.'
        '- External operational risk.'
        '- Labor availability.'
        '- Inventory coverage.'
        ''
        'Strategic decision variables optimized by GA:'
        '- Capacity multiplier.'
        '- Cost-policy multiplier.'
        '- Resilience-investment level.'
        '- Inventory-buffer level.'
        '- Workforce-flexibility level.'
        '- Supplier-redundancy level.'
        ''
        'Management interpretation:'
        'The simulated organization must decide how to adjust capacity, cost policy, resilience investment, inventory buffers, workforce flexibility, and supplier redundancy across a distributed operating network while balancing service level, utilization, expected cost, and residual risk.'
        ''
        'Purpose:'
        'The case is a reproducible simulation-based benchmark for testing whether the GATrESN digital twin can forecast operational states and prescribe adaptive strategic operations decisions under temporal uncertainty.'
    };
    writecell(context, fullfile(resultsDir, 'GATrESN_case_study_context.txt'), ...
        'FileType', 'text');
end

function useParallel = startParallelPool(requestedWorkers)
    useParallel = false;
    if isempty(ver('parallel'))
        fprintf('Parallel Computing Toolbox not detected. Running serial GA optimization.\n');
        return;
    end

    try
        pool = gcp('nocreate');
        if isempty(pool)
            cluster = parcluster('local');
            workers = min(requestedWorkers, cluster.NumWorkers);
            parpool('local', workers);
        elseif pool.NumWorkers ~= requestedWorkers
            fprintf('Using existing parallel pool with %d workers.\n', pool.NumWorkers);
        end
        useParallel = true;
    catch ME
        fprintf('Parallel pool could not be started: %s\n', ME.message);
        fprintf('Running serial GA optimization.\n');
    end
end

function [site, product, period, forecastDemand, forecastRisk, capacityMultiplier, ...
    costMultiplier, resilienceInvestment, inventoryBuffer, workforceFlexibility, ...
    supplierRedundancy, optimizedCapacity, serviceLevel, utilization, expectedCost, ...
    residualRisk, strategicScore] = optimizeDecisionInstance( ...
    i, YHatTest, metaTest, config)

    forecastDemand = max(YHatTest(i, 1), 1);
    forecastRisk = min(max(YHatTest(i, 2), 0), 1);
    site = metaTest.Site(i);
    product = metaTest.Product(i);
    period = metaTest.Period(i);

    baseCapacity = metaTest.BaseCapacity(i);
    baseUnitCost = metaTest.UnitCost(i);

    objective = @(x) -robustStrategicUtility(x, forecastDemand, forecastRisk, ...
        baseCapacity, baseUnitCost, config, i);
    lowerBounds = [0.80, 0.82, 0.00, 0.00, 0.00, 0.00];
    upperBounds = [1.40, 1.28, 1.00, 1.00, 1.00, 1.00];
    gaSeed = config.seed + 1000 + i;

    [bestDecision, bestFitness] = simpleGA(objective, lowerBounds, upperBounds, ...
        config.gaPopulation, config.gaGenerations, config.gaMutationRate, gaSeed);

    capacityMultiplier = bestDecision(1);
    costMultiplier = bestDecision(2);
    resilienceInvestment = bestDecision(3);
    inventoryBuffer = bestDecision(4);
    workforceFlexibility = bestDecision(5);
    supplierRedundancy = bestDecision(6);
    strategicScore = -bestFitness;

    [optimizedCapacity, serviceLevel, utilization, expectedCost, residualRisk, ~] = ...
        evaluateStrategicDecision(bestDecision, forecastDemand, forecastRisk, baseCapacity, baseUnitCost);
end

function text = logicalText(value)
    if value
        text = 'true';
    else
        text = 'false';
    end
end

function ops = generateOperationsData(nSites, nProducts, nPeriods)
    rows = nSites * nProducts * nPeriods;
    Site = zeros(rows, 1);
    Product = zeros(rows, 1);
    Period = zeros(rows, 1);
    Demand = zeros(rows, 1);
    BaseCapacity = zeros(rows, 1);
    UnitCost = zeros(rows, 1);
    ServicePressure = zeros(rows, 1);
    ExternalRisk = zeros(rows, 1);
    LaborAvailability = zeros(rows, 1);
    InventoryCoverage = zeros(rows, 1);

    idx = 1;
    for s = 1:nSites
        siteScale = 0.85 + 0.25 * rand();
        siteRisk = 0.10 + 0.22 * rand();
        disruptionMemory = 0;
        for p = 1:nProducts
            productScale = 0.80 + 0.45 * rand();
            productVolatility = 5 + 8 * rand();
            demandMemory = 0;
            for t = 1:nPeriods
                if rand() < 0.018
                    disruptionMemory = disruptionMemory + 0.18 + 0.22 * rand();
                end
                disruptionMemory = 0.88 * disruptionMemory;
                if rand() < 0.028
                    demandMemory = demandMemory + 16 * rand();
                end
                demandMemory = 0.82 * demandMemory;

                trend = 90 * siteScale * productScale + 0.08 * t;
                seasonality = 14 * sin(2 * pi * t / 12 + 0.35 * p) ...
                    + 7 * cos(2 * pi * t / 24 + 0.20 * s);
                disruption = 18 * (rand() < 0.035) * rand() + demandMemory;
                demand = max(8, trend + seasonality + productVolatility * randn() + disruption);
                capacity = max(20, 105 * siteScale + 6 * sin(2 * pi * t / 18) + 5 * randn() ...
                    - 12 * disruptionMemory);
                unitCost = max(5, 42 + 1.5 * s + 0.8 * p + 3 * sin(2 * pi * t / 20) ...
                    + 2.5 * randn() + 5 * disruptionMemory);
                labor = min(max(0.75 + 0.12 * sin(2 * pi * t / 16) + 0.08 * randn() ...
                    - 0.18 * disruptionMemory, 0.40), 1.0);
                inventory = min(max(0.65 + 0.16 * cos(2 * pi * t / 14 + p) + 0.10 * randn() ...
                    - 0.12 * disruptionMemory, 0.15), 1.25);
                risk = min(max(siteRisk + 0.13 * randn() + 0.18 * (labor < 0.65) ...
                    + 0.10 * (inventory < 0.45) + 0.40 * disruptionMemory, 0), 1);
                pressure = demand / max(capacity, 1);

                Site(idx) = s;
                Product(idx) = p;
                Period(idx) = t;
                Demand(idx) = demand;
                BaseCapacity(idx) = capacity;
                UnitCost(idx) = unitCost;
                ServicePressure(idx) = pressure;
                ExternalRisk(idx) = risk;
                LaborAvailability(idx) = labor;
                InventoryCoverage(idx) = inventory;
                idx = idx + 1;
            end
        end
    end

    ops = table(Site, Product, Period, Demand, BaseCapacity, UnitCost, ...
        ServicePressure, ExternalRisk, LaborAvailability, InventoryCoverage);
end

function [X, Y, meta] = buildSupervisedDataset(ops, nLags, horizon)
    featureNames = {'Demand', 'BaseCapacity', 'UnitCost', 'ServicePressure', ...
        'ExternalRisk', 'LaborAvailability', 'InventoryCoverage'};
    targetNames = {'Demand', 'ExternalRisk'};
    X = [];
    Y = [];
    meta = table();
    groups = unique([ops.Site, ops.Product], 'rows');

    for g = 1:size(groups, 1)
        idx = ops.Site == groups(g, 1) & ops.Product == groups(g, 2);
        block = sortrows(ops(idx, :), 'Period');
        values = table2array(block(:, featureNames));
        targets = table2array(block(:, targetNames));

        for t = nLags:(height(block) - horizon)
            lagBlock = values(t-nLags+1:t, :);
            X = [X; lagBlock(:)']; %#ok<AGROW>
            Y = [Y; targets(t+horizon, :)]; %#ok<AGROW>
            meta = [meta; block(t+horizon, {'Site', 'Product', 'Period', 'BaseCapacity', 'UnitCost'})]; %#ok<AGROW>
        end
    end

    [X, mu, sigma] = zscore(X);
    sigma(sigma == 0) = 1;
    X = (X - 0) ./ 1;
end

function esn = initializeESN(inputSize, reservoirSize, spectralRadius, inputScale, leakRate)
    Win = inputScale * (2 * rand(reservoirSize, inputSize) - 1);
    W = 2 * rand(reservoirSize, reservoirSize) - 1;
    eigValues = eig(W);
    W = W .* (spectralRadius / max(abs(eigValues)));
    esn = struct('Win', Win, 'W', W, 'LeakRate', leakRate);
end

function states = computeESNStates(esn, X)
    n = size(X, 1);
    reservoirSize = size(esn.W, 1);
    states = zeros(n, reservoirSize);
    state = zeros(reservoirSize, 1);

    for i = 1:n
        u = X(i, :)';
        candidate = tanh(esn.Win * u + esn.W * state);
        state = (1 - esn.LeakRate) * state + esn.LeakRate * candidate;
        states(i, :) = state';
    end
end

function A = attentionFeatures(Z, nLags, nHeads)
    n = size(Z, 1);
    d = size(Z, 2);
    headDim = floor(d / nHeads);
    A = zeros(n, nHeads);

    for i = 1:n
        startIdx = max(1, i - nLags + 1);
        context = Z(startIdx:i, :);
        query = Z(i, :);

        for h = 1:nHeads
            cols = (h-1)*headDim + 1:min(h*headDim, d);
            q = query(cols);
            k = context(:, cols);
            scores = (k * q') / sqrt(numel(cols));
            weights = exp(scores - max(scores));
            weights = weights ./ sum(weights);
            attended = weights' * context(:, cols);
            A(i, h) = mean(attended);
        end
    end
end

function score = strategicUtility(x, forecastDemand, forecastRisk, baseCapacity, baseUnitCost)
    x = completeDecisionVector(x);
    capacityMultiplier = x(1);
    costMultiplier = x(2);
    resilienceInvestment = x(3);
    inventoryBuffer = x(4);
    workforceFlexibility = x(5);
    supplierRedundancy = x(6);

    capacity = baseCapacity * capacityMultiplier * (1 + 0.08 * workforceFlexibility);
    availabilityBuffer = 1 + 0.10 * inventoryBuffer + 0.06 * supplierRedundancy;
    effectiveCapacity = capacity * availabilityBuffer;
    qualityPenalty = 1 - 0.18 * max(0, 0.95 - costMultiplier) / 0.13;
    qualityPenalty = min(max(qualityPenalty, 0.82), 1.0);
    fulfilled = min(forecastDemand, effectiveCapacity) * qualityPenalty;
    serviceLevel = fulfilled / forecastDemand;
    utilization = fulfilled / effectiveCapacity;
    cost = fulfilled * baseUnitCost * costMultiplier ...
        + 420 * resilienceInvestment ...
        + 160 * inventoryBuffer ...
        + 280 * workforceFlexibility ...
        + 360 * supplierRedundancy ...
        + 0.035 * baseCapacity * baseUnitCost * max(0, capacityMultiplier - 1);
    normalizedCost = min(cost / max(forecastDemand * baseUnitCost * 1.55, 1), 1.7);
    riskMitigation = 0.35 * resilienceInvestment + 0.18 * inventoryBuffer ...
        + 0.20 * workforceFlexibility + 0.25 * supplierRedundancy;
    complexityRisk = 0.025 * max(0, capacityMultiplier - 1.15) ...
        + 0.035 * max(0, 0.92 - costMultiplier);
    residualRisk = min(max(forecastRisk * (1 - riskMitigation) + complexityRisk, 0), 1);
    utilizationScore = 1 - min(abs(utilization - 0.85) / 0.85, 1);
    serviceShortfallPenalty = max(0, 0.92 - serviceLevel);
    extremePolicyPenalty = mean(abs(x - [1.05, 1.00, 0.35, 0.30, 0.30, 0.30]));

    score = 0.34 * serviceLevel ...
        + 0.23 * utilizationScore ...
        + 0.21 * (1 - min(normalizedCost, 1)) ...
        + 0.22 * (1 - residualRisk) ...
        - 0.10 * serviceShortfallPenalty ...
        - 0.035 * extremePolicyPenalty;
end

function score = robustStrategicUtility(x, forecastDemand, forecastRisk, baseCapacity, baseUnitCost, config, decisionIndex)
    nScenarios = config.monteCarloScenarios;
    if nScenarios <= 1
        score = strategicUtility(x, forecastDemand, forecastRisk, baseCapacity, baseUnitCost);
        return;
    end

    rng(config.seed + 50000 + decisionIndex, 'twister');
    scenarioScores = zeros(nScenarios, 1);

    for s = 1:nScenarios
        disruptionEvent = rand() < 0.12;
        demandShock = max(0.55, 1 + 0.16 * randn() + 0.20 * disruptionEvent * rand());
        riskShock = min(max(forecastRisk + 0.10 * randn() + 0.18 * disruptionEvent, 0), 1);
        capacityShock = max(0.62, 1 + 0.10 * randn() - 0.18 * disruptionEvent * rand());
        costShock = max(0.72, 1 + 0.12 * randn() + 0.16 * disruptionEvent * rand());

        scenarioScores(s) = strategicUtility(x, ...
            forecastDemand * demandShock, ...
            riskShock, ...
            baseCapacity * capacityShock, ...
            baseUnitCost * costShock);
    end

    meanScore = mean(scenarioScores);
    downsidePenalty = std(scenarioScores) + max(0, 0.72 - localPercentile(scenarioScores, 10));
    tailPenalty = max(0, meanScore - localPercentile(scenarioScores, 5));
    score = meanScore - 0.22 * downsidePenalty - 0.14 * tailPenalty;
end

function x = completeDecisionVector(x)
    if numel(x) < 6
        x = [x(:)' zeros(1, 6 - numel(x))];
    else
        x = x(:)';
    end
end

function value = localPercentile(x, p)
    x = sort(x(:));
    if isempty(x)
        value = NaN;
        return;
    end
    position = 1 + (numel(x) - 1) * p / 100;
    lowerIndex = floor(position);
    upperIndex = ceil(position);
    if lowerIndex == upperIndex
        value = x(lowerIndex);
    else
        weight = position - lowerIndex;
        value = (1 - weight) * x(lowerIndex) + weight * x(upperIndex);
    end
end

function [bestX, bestFitness] = simpleGA(objective, lb, ub, populationSize, generations, mutationRate, seed)
    rng(seed, 'twister');
    nVars = numel(lb);
    population = lb + rand(populationSize, nVars) .* (ub - lb);
    fitness = evaluatePopulation(objective, population);

    for gen = 1:generations
        [fitness, order] = sort(fitness);
        population = population(order, :);
        eliteCount = max(2, round(0.10 * populationSize));
        newPopulation = population(1:eliteCount, :);

        while size(newPopulation, 1) < populationSize
            parent1 = tournament(population, fitness);
            parent2 = tournament(population, fitness);
            alpha = rand();
            child = alpha * parent1 + (1 - alpha) * parent2;

            if rand() < mutationRate
                mutation = 0.08 * randn(1, nVars) .* (ub - lb);
                child = child + mutation;
            end

            child = min(max(child, lb), ub);
            newPopulation = [newPopulation; child]; %#ok<AGROW>
        end

        population = newPopulation;
        fitness = evaluatePopulation(objective, population);
    end

    [bestFitness, idx] = min(fitness);
    bestX = population(idx, :);
end

function fitness = evaluatePopulation(objective, population)
    fitness = zeros(size(population, 1), 1);
    for i = 1:size(population, 1)
        fitness(i) = objective(population(i, :));
    end
end

function parent = tournament(population, fitness)
    candidates = randi(size(population, 1), [3, 1]);
    [~, bestLocal] = min(fitness(candidates));
    parent = population(candidates(bestLocal), :);
end

function e = rmse(y, yhat)
    e = sqrt(mean((y(:) - yhat(:)).^2));
end

function e = mae(y, yhat)
    e = mean(abs(y(:) - yhat(:)));
end

function plotForecast(y, yhat, outputPath)
    figure('Color', 'w', 'Position', [100 100 1000 520]);
    plot(y, 'LineWidth', 1.6); hold on;
    plot(yhat, 'LineWidth', 1.6);
    grid on;
    xlabel('Test Observation');
    ylabel('Demand');
    legend({'Actual', 'Predicted'}, 'Location', 'best');
    title('GATrESN Demand Forecast');
    exportgraphics(gcf, outputPath, 'Resolution', 300);
end

function plotDecisionSeries(results, metricName, chartTitle, outputPath)
    figure('Color', 'w', 'Position', [100 100 1000 520]);
    plot(results.(metricName), 'LineWidth', 1.8);
    grid on;
    xlabel('Optimized Decision Instance');
    ylabel(metricName);
    title(chartTitle);
    exportgraphics(gcf, outputPath, 'Resolution', 300);
end
