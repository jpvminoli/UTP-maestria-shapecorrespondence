% DEMOILVARGPLVM1 Run variational GPLVM on oil data.

% VARGPLVM

% Fix seeds
randn('seed', 1e5);
rand('seed', 1e5);

dataSetName = 'oil';
experimentNo = 1;
printDiagram = 1;

% load data
[Y, lbls] = lvmLoadData(dataSetName);

% Set up model
options = vargplvmOptions('dtcvar');
options.kern = {'rbfard2', 'bias', 'white'};
%options.kern = 'rbfardjit';
options.numActive = 50; 
%options.tieParam = 'tied';  

options.optimiser = 'scg2';
latentDim = 10;
d = size(Y, 2);

% demo using the variational inference method for the gplvm model
model = vargplvmCreate(latentDim, d, Y, options);
%
model = vargplvmParamInit(model, model.m, model.X); 
model.vardist.covars = 0.5*ones(size(model.vardist.covars)) + 0.001*randn(size(model.vardist.covars));
model.learnBeta=1;

% Optimise the model.
iters = 200;
display = 1;

model = vargplvmOptimise(model, display, iters);

capName = dataSetName;
capName(1) = upper(capName(1));
modelType = model.type;
modelType(1) = upper(modelType(1));
save(['dem' capName modelType num2str(experimentNo) '.mat'], 'model');

% order wrt to the inputScales 
mm = vargplvmReduceModel(model,2);
%% plot the two largest twe latent dimensions 
if exist('printDiagram') & printDiagram
  lvmPrintPlot(mm, lbls, capName, experimentNo);
end
