%% AI-Driven Digital Twin Framework for Strategic Operations Management
% Simulation-based case study for a strategic operations digital twin.

clear; clc; close all;
rng(42);

%% Configuration
nPeriods = 120;
t = (1:nPeriods)';

outputDir = fullfile(fileparts(mfilename('fullpath')), '..', 'results');
figureDir = fullfile(fileparts(mfilename('fullpath')), '..', 'figures');
dataDir = fullfile(fileparts(mfilename('fullpath')), '..', 'data');

if ~exist(outputDir, 'dir'), mkdir(outputDir); end
if ~exist(figureDir, 'dir'), mkdir(figureDir); end
if ~exist(dataDir, 'dir'), mkdir(dataDir); end

%% Synthetic operating environment
trend = linspace(80, 115, nPeriods)';
seasonality = 12 * sin(2 * pi * t / 12);
randomShock = 8 * randn(nPeriods, 1);
demand = max(20, trend + seasonality + randomShock);

baseCapacity = 105 + 6 * sin(2 * pi * t / 24) + 4 * randn(nPeriods, 1);
unitCost = 45 + 4 * sin(2 * pi * t / 18) + 3 * randn(nPeriods, 1);
externalRisk = min(max(0.20 + 0.12 * randn(nPeriods, 1), 0), 1);

operationsData = table(t, demand, baseCapacity, unitCost, externalRisk, ...
    'VariableNames', {'Period', 'Demand', 'BaseCapacity', 'UnitCost', 'ExternalRisk'});

writetable(operationsData, fullfile(dataDir, 'synthetic_operations_data.csv'));

%% Strategic policies
strategies = {
    'Conservative', 0.95, 0.95, 0.85;
    'Efficiency',   0.90, 0.88, 0.70;
    'Expansion',    1.18, 1.12, 0.78;
    'Resilience',   1.08, 1.18, 0.55;
    'AI-Adaptive',  1.00, 1.00, 0.60
};

nStrategies = size(strategies, 1);
results = table();

%% Digital twin simulation
for i = 1:nStrategies
    name = string(strategies{i, 1});
    capacityMultiplier = strategies{i, 2};
    costMultiplier = strategies{i, 3};
    riskMultiplier = strategies{i, 4};

    if name == "AI-Adaptive"
        forecastDemand = movmean(demand, [5 0]);
        adaptiveFactor = min(max(forecastDemand ./ baseCapacity, 0.88), 1.20);
        capacity = baseCapacity .* adaptiveFactor;
        cost = unitCost .* (0.98 + 0.10 * max(adaptiveFactor - 1, 0));
        risk = min(max(externalRisk .* 0.58 + 0.10 * abs(adaptiveFactor - 1), 0), 1);
    else
        capacity = baseCapacity .* capacityMultiplier;
        cost = unitCost .* costMultiplier;
        risk = min(max(externalRisk .* riskMultiplier, 0), 1);
    end

    fulfilledDemand = min(demand, capacity);
    serviceLevel = fulfilledDemand ./ demand;
    utilization = fulfilledDemand ./ capacity;
    operatingCost = fulfilledDemand .* cost;

    normalizedCost = normalize01(operatingCost);
    targetUtilization = 0.85;
    utilizationScore = 1 - min(abs(utilization - targetUtilization) ./ targetUtilization, 1);

    strategicScore = 0.35 * serviceLevel ...
        + 0.25 * utilizationScore ...
        + 0.20 * (1 - normalizedCost) ...
        + 0.20 * (1 - risk);

    strategyResults = table( ...
        repmat(name, nPeriods, 1), t, demand, capacity, fulfilledDemand, ...
        serviceLevel, utilization, operatingCost, risk, strategicScore, ...
        'VariableNames', {'Strategy', 'Period', 'Demand', 'Capacity', ...
        'FulfilledDemand', 'ServiceLevel', 'Utilization', 'OperatingCost', ...
        'Risk', 'StrategicScore'});

    results = [results; strategyResults]; %#ok<AGROW>
end

writetable(results, fullfile(outputDir, 'scenario_results.csv'));

%% Summary table
summary = groupsummary(results, 'Strategy', 'mean', ...
    {'ServiceLevel', 'Utilization', 'OperatingCost', 'Risk', 'StrategicScore'});
summary = sortrows(summary, 'mean_StrategicScore', 'descend');
writetable(summary, fullfile(outputDir, 'strategy_summary.csv'));

disp(summary);

%% Figures
plotMetric(results, 'ServiceLevel', 'Service Level', fullfile(figureDir, 'service_level.png'));
plotMetric(results, 'OperatingCost', 'Operating Cost', fullfile(figureDir, 'operating_cost.png'));
plotMetric(results, 'Risk', 'Operational Risk', fullfile(figureDir, 'operational_risk.png'));
plotMetric(results, 'StrategicScore', 'Strategic Performance Score', fullfile(figureDir, 'strategic_score.png'));

%% Local functions
function y = normalize01(x)
    minX = min(x);
    maxX = max(x);
    if maxX == minX
        y = zeros(size(x));
    else
        y = (x - minX) ./ (maxX - minX);
    end
end

function plotMetric(results, metricName, yLabelText, outputPath)
    figure('Color', 'w', 'Position', [100 100 1000 560]);
    strategyNames = unique(results.Strategy, 'stable');
    hold on;

    for k = 1:numel(strategyNames)
        idx = results.Strategy == strategyNames(k);
        plot(results.Period(idx), results.(metricName)(idx), 'LineWidth', 1.8);
    end

    grid on;
    xlabel('Period');
    ylabel(yLabelText);
    legend(strategyNames, 'Location', 'best');
    title([yLabelText ' by Strategic Scenario']);
    exportgraphics(gcf, outputPath, 'Resolution', 300);
end
