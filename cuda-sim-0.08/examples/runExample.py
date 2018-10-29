from __future__ import print_function
from __future__ import division
from builtins import str
from builtins import range
from past.utils import old_div
import numpy as np
import time, os

import cudasim
import cudasim.EulerMaruyama as EulerMaruyama
import cudasim.Gillespie as Gillespie
import cudasim.Lsoda as Lsoda
import cudasim.SBMLParser as Parser


##### parameters #####

# Location of the SBML model file
xmlModel = ""

# Name of the model
name = ""

# Type of integration
#integrationType = "ODE" 
#integrationType = "SDE" 
integrationType = "MJP"

# Location of the file containing the parameters
parameterFile = ""

# Location of the file containing the initialization values for the different species
speciesFile = ""

# Length of simulation
simulationLength = 50

# Number of equally distributed datapoints to be saved
datapoints = 100

# Size of timesteps (only relevant for SDEs)
dt = 0.01

# Number of repeated simulation for each set of parameters and species (ignored for ODE)
beta = 1

# Location of the folder for saving the results
resultFolder = ""

# Location of the temporary folder for model specific CUDA codes
# temp folder in this file's folder will be created if not specified  
temp = None




##### initialization #####

# create temp folder
if(temp == None):
    temp = os.path.join(os.path.split(os.path.realpath(__file__))[0],"temp")
    try:
        os.mkdir(temp)
    except:
        pass
# create result folder
try:
    os.mkdir(os.path.realpath(resultFolder))
except:
    pass

# default naming
if(name==""):
    name="model"

# create CUDA code from SBML model
Parser.importSBMLCUDA([xmlModel],[integrationType],ModelName=[name],method=None,outpath=temp)

#determining the timepoints for the output
timepoints = old_div(np.array(list(range(datapoints+1)),dtype=np.float32) * simulationLength,datapoints) 

# reading in the CUDA code
cudaCode = os.path.join(temp, name + ".cu")

# reading in parameters
parameters = []
inFile = open(parameterFile,'r').read()
lines = inFile.split("\n")
for i in range(len(lines)):
    if(lines[i].strip() == ""):
        continue
    parameters.append([])
    lineParam = lines[i].strip().split(" ")
    for j in range(len(lineParam)):
        parameters[i].append(lineParam[j])
# reading in species
species = []
inFile = open(speciesFile,'r').read()
lines = inFile.split("\n")
for i in range(len(lines)):
    if(lines[i].strip() == ""):
        continue
    species.append([])
    lineSpecies = lines[i].strip().split(" ")
    for j in range(len(lineSpecies)):
        species[i].append(lineSpecies[j])


# create model
print("Create model..", end=' ')
if(integrationType == "SDE"):
    modeInstance = EulerMaruyama.EulerMaruyama(timepoints, cudaCode, beta=beta, dt=dt)
elif(integrationType == "MJP"):
    modeInstance = Gillespie.Gillespie(timepoints, cudaCode, beta=beta, dt=dt)
else:
    modeInstance = Lsoda.Lsoda(timepoints, cudaCode, dt=dt)

print("..calculating..", end=' ')
result = modeInstance.run(parameters, species)
print("..finished.")

# write output
print("Write output.")
out = open(os.path.join(resultFolder,name+"_result.txt"),'w')
print("- - -", end=' ', file=out)
for i in range(len(timepoints)):
    print(timepoints[i], end=' ', file=out)
print("", file=out)
for i in range(len(result)):
        for j in range(len(result[i])):
            for l in range(len(result[i][0][0])):
                print('e:' + str(i), 'b:'+str(j),'s:'+str(l), end=' ', file=out)
                for k in range(len(timepoints)):
                    print(result[i][j][k][l], end=' ', file=out)
                print("", file=out)
                    
                        
out.close()
        
        