import os
import re

from numpy import *

from cudasim.writers.Writer import Writer
from cudasim.cuda_helpers import renameMathFunctions

class GillespieCUDAWriter(Writer):
    def __init__(self, sbmlFileName, modelName="", inputPath="", outputPath=""):
        Writer.__init__(self, sbmlFileName, modelName, inputPath, outputPath)
        self.out_file = open(os.path.join(outputPath, self.parsedModel.name + ".cu"), "w")

    def rename(self):
        """
        This function renames parts of self.parsedModel to meet the specific requirements of this writer.
        This behaviour replaces the previous approach of subclassing the parser to produce different results depending
        on the which writer was intended to be used.
        """

        # Pad single-digit parameter names with a leading zero
        for i in range(self.comp-1, len(self.parsedModel.parameterId)):
            old_name = self.parsedModel.parameterId[i]
            num = old_name[len('parameter'):]
            if len(num) < 2:
                self.parsedModel.parameterId[i] = '0' + str(num)

        # Pad single-digit species names with a leading zero
        for i in range(0, len(self.parsedModel.speciesId)):
            old_name = self.parsedModel.speciesId[i]
            num = old_name[len('species'):]
            if len(num) < 2:
                self.parsedModel.speciesId[i] = '0' + str(num)

        (mathCuda, mathPython) = renameMathFunctions()
        mathCuda.append('t')

    def write(self, useMoleculeCounts=False):

        p = re.compile('\s')
        # Open the outfile
    
        numSpecies = len(self.parsedModel.species)
    
        numEvents = len(self.parsedModel.listOfEvents)
        numRules = len(self.parsedModel.listOfRules)
        num = numEvents + numRules
    
        # Write number of parameters and species
        self.out_file.write("#define NSPECIES " + str(numSpecies) + "\n")
        self.out_file.write("#define NPARAM " + str(len(self.parsedModel.parameterId)) + "\n")
        self.out_file.write("#define NREACT " + str(self.parsedModel.numReactions) + "\n")
        self.out_file.write("\n")
    
        if num > 0:
            self.out_file.write("#define leq(a,b) a<=b\n")
            self.out_file.write("#define neq(a,b) a!=b\n")
            self.out_file.write("#define geq(a,b) a>=b\n")
            self.out_file.write("#define lt(a,b) a<b\n")
            self.out_file.write("#define gt(a,b) a>b\n")
            self.out_file.write("#define eq(a,b) a==b\n")
            self.out_file.write("#define and_(a,b) a&&b\n")
            self.out_file.write("#define or_(a,b) a||b\n")
    
        for i in range(0, len(self.parsedModel.listOfFunctions)):
            self.out_file.write("__device__ float " + self.parsedModel.listOfFunctions[i].getId() + "(")
            for j in range(0, self.parsedModel.listOfFunctions[i].getNumArguments()):
                self.out_file.write("float " + self.parsedModel.FunctionArgument[i][j])
                if j < (self.parsedModel.listOfFunctions[i].getNumArguments() - 1):
                    self.out_file.write(",")
            self.out_file.write("){\n    return ")
            self.out_file.write(self.parsedModel.FunctionBody[i])
            self.out_file.write(";\n}\n")
            self.out_file.write("")
    
        self.out_file.write("\n\n__constant__ int smatrix[]={\n")
        for i in range(0, len(self.parsedModel.stoichiometricMatrix[0])):
            for j in range(0, len(self.parsedModel.stoichiometricMatrix)):
                self.out_file.write("    " + repr(self.parsedModel.stoichiometricMatrix[j][i]))
                if not (i == (len(self.parsedModel.stoichiometricMatrix) - 1) and (j == (len(self.parsedModel.stoichiometricMatrix[0]) - 1))):
                    self.out_file.write(",")
            self.out_file.write("\n")
    
        self.out_file.write("};\n\n\n")
    
        if useMoleculeCounts:
                self.out_file.write("__device__ void hazards(int *y, float *h, float t, int tid){\n")
                self.out_file.write("        // Assume rate law expressed in terms of molecule counts \n")
        else:
            self.out_file.write("__device__ void hazards(int *yCounts, float *h, float t, int tid){")
    
            self.out_file.write("""
            // Calculate concentrations from molecule counts
            int y[NSPECIES];
            """)
    
            for i in range(0, numSpecies):
                volumeString = "tex2D(param_tex," + repr(self.parsedModel.speciesCompartmentList[i]) + ",tid)"
                self.out_file.write( "y[%s] = yCounts[%s] / (6.022E23 * %s);\n" % (i, i, volumeString) )
    
        # write rules and events
        for i in range(0, len(self.parsedModel.listOfRules)):
            if self.parsedModel.listOfRules[i].isRate():
                self.out_file.write("    ")
                if not (self.parsedModel.ruleVariable[i] in self.parsedModel.speciesId):
                    self.out_file.write(self.parsedModel.ruleVariable[i])
                else:
                    string = "y[" + repr(self.parsedModel.speciesId.index(self.parsedModel.ruleVariable[i])) + "]"
                    self.out_file.write(string)
                self.out_file.write("=")
    
                string = self.parsedModel.ruleFormula[i]
                for q in range(0, len(self.parsedModel.speciesId)):
                    string = self.rep(string, self.parsedModel.speciesId[q], 'y[' + repr(q) + ']')
                for q in range(0, len(self.parsedModel.parameterId)):
                    if not (self.parsedModel.parameterId[q] in self.parsedModel.ruleVariable):
                        flag = False
                        for r in range(0, len(self.parsedModel.EventVariable)):
                            if self.parsedModel.parameterId[q] in self.parsedModel.EventVariable[r]:
                                flag = True
                        if not flag:
                            string = self.rep(string, self.parsedModel.parameterId[q], 'tex2D(param_tex,' + repr(q) + ',tid)')
    
                self.out_file.write(string)
                self.out_file.write(";\n")
    
        for i in range(0, len(self.parsedModel.listOfEvents)):
            self.out_file.write("    if( ")
            self.out_file.write(self.mathMLConditionParserCuda(self.parsedModel.EventCondition[i]))
            self.out_file.write("){\n")
            listOfAssignmentRules = self.parsedModel.listOfEvents[i].getListOfEventAssignments()
            for j in range(0, len(listOfAssignmentRules)):
                self.out_file.write("        ")
                if not (self.parsedModel.EventVariable[i][j] in self.parsedModel.speciesId):
                    self.out_file.write(self.parsedModel.EventVariable[i][j])
                else:
                    string = "y[" + repr(self.parsedModel.speciesId.index(self.parsedModel.EventVariable[i][j])) + "]"
                    self.out_file.write(string)
                self.out_file.write("=")
    
                string = self.parsedModel.EventFormula[i][j]
                for q in range(0, len(self.parsedModel.speciesId)):
                    string = self.rep(string, self.parsedModel.speciesId[q], 'y[' + repr(q) + ']')
                for q in range(0, len(self.parsedModel.parameterId)):
                    if not (self.parsedModel.parameterId[q] in self.parsedModel.ruleVariable):
                        flag = False
                        for r in range(0, len(self.parsedModel.EventVariable)):
                            if self.parsedModel.parameterId[q] in self.parsedModel.EventVariable[r]:
                                flag = True
                        if not flag:
                            string = self.rep(string, self.parsedModel.parameterId[q], 'tex2D(param_tex,' + repr(q) + ',tid)')
    
                self.out_file.write(string)
                self.out_file.write(";\n")
            self.out_file.write("    }\n")
    
        self.out_file.write("\n")
    
        for i in range(0, len(self.parsedModel.listOfRules)):
            if self.parsedModel.listOfRules[i].isAssignment():
                self.out_file.write("    ")
                if not (self.parsedModel.ruleVariable[i] in self.parsedModel.speciesId):
                    self.out_file.write("float ")
                    self.out_file.write(self.parsedModel.ruleVariable[i])
                else:
                    string = "y[" + repr(self.parsedModel.speciesId.index(self.parsedModel.ruleVariable[i])) + "]"
                    self.out_file.write(string)
                self.out_file.write("=")
    
                string = self.mathMLConditionParserCuda(self.parsedModel.ruleFormula[i])
                for q in range(0, len(self.parsedModel.speciesId)):
                    string = self.rep(string, self.parsedModel.speciesId[q], 'y[' + repr(q) + ']')
                for q in range(0, len(self.parsedModel.parameterId)):
                    if not (self.parsedModel.parameterId[q] in self.parsedModel.ruleVariable):
                        flag = False
                        for r in range(0, len(self.parsedModel.EventVariable)):
                            if self.parsedModel.parameterId[q] in self.parsedModel.EventVariable[r]:
                                flag = True
                        if not flag:
                            string = self.rep(string, self.parsedModel.parameterId[q], 'tex2D(param_tex,' + repr(q) + ',tid)')
                self.out_file.write(string)
                self.out_file.write(";\n")
        self.out_file.write("\n")
    
        for i in range(0, self.parsedModel.numReactions):
    
            if useMoleculeCounts:
                self.out_file.write("    h[" + repr(i) + "] = ")
            else:
                self.out_file.write("    h[" + repr(i) + "] = 6.022E23 * ")
    
            string = self.parsedModel.kineticLaw[i]
            for q in range(0, len(self.parsedModel.speciesId)):
                string = self.rep(string, self.parsedModel.speciesId[q], 'y[' + repr(q) + ']')
            for q in range(0, len(self.parsedModel.parameterId)):
                if not (self.parsedModel.parameterId[q] in self.parsedModel.ruleVariable):
                    flag = False
                    for r in range(0, len(self.parsedModel.EventVariable)):
                        if self.parsedModel.parameterId[q] in self.parsedModel.EventVariable[r]:
                            flag = True
                    if not flag:
                        string = self.rep(string, self.parsedModel.parameterId[q], 'tex2D(param_tex,' + repr(q) + ',tid)')
    
            string = p.sub('', string)
            self.out_file.write(string + ";\n")
    
        self.out_file.write("\n")
        self.out_file.write("}\n\n")
