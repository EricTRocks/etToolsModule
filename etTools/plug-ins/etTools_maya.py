import os
import sys
import json

import maya
from maya import cmds
import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as OpenMayaAnim
import maya.api.OpenMayaUI as OpenMayaUI

try:
    from shiboken import wrapInstance
except:
    from shiboken2 import wrapInstance


def getMayaWindow():
    ptr = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(long(ptr), QtWidgets.QWidget)

def maya_useNewAPI():
    """
    The presence of this function tells Maya that the plugin produces, and
    expects to be passed, objects created using the Maya Python API 2.0.
    """
    pass

# ========
# Helpers
# ========

# =========
# Commands
# =========
class ETToolsMatchXfoCmd(om2.MPxCommand):

    def __init__(self):
        om2.MPxCommand.__init__(self)
        self.dagModifier = om2.MDagModifier()
        self.dgModifier = om2.MDGModifier()
        self.selList = om2.MSelectionList()
        self.matchScale = True
        self.matchRotation = True
        self.matchTranslation = True
        self.origTransforms = []

    # Invoked when the command is run.
    def doIt(self, args):
       
        try:
            argdb = om2.MArgDatabase(self.syntax(), args)
        except RuntimeError:
            om2.MGlobal.displayError('Error while parsing arguments:\n#\t# If passing in list of nodes, also check that node names exist in scene.')
            return False

        if argdb.isFlagSet("scale"):
            self.matchScale = argdb.flagArgumentBool("scale", 0)

        if argdb.isFlagSet("rotation"):
            self.matchRotation = argdb.flagArgumentBool("rotation", 0)

        if argdb.isFlagSet("translation"):
            self.matchTranslation = argdb.flagArgumentBool("translation", 0)
            print self.matchTranslation

        self.selList.copy(argdb.getObjectList())        
        
        if self.selList.length() < 2:
            om2.MGlobal.displayWarning('etMatchXfo: You must select target objects, then a source object.')
            return False

        self.redoIt()

    def wMtxFromMObj(self, node_mob):

        if not node_mob.hasFn(om2.MFn.kDagNode):
            return None
     
        dagNode = om2.MFnDagNode(node_mob)
        worldMatrixPlug = dagNode.findPlug('worldMatrix', False)
        wmElementPlug = worldMatrixPlug.elementByLogicalIndex(0)
     
        wmElementPlugMObj = wmElementPlug.asMObject()
        matrixData = om2.MFnMatrixData(wmElementPlugMObj)

        return matrixData.transformation()

    def redoIt(self):
        srcWMtx = self.wMtxFromMObj(self.selList.getDependNode(self.selList.length() - 1))
        srcWSc = srcWMtx.scale(om2.MSpace.kWorld)
        srcWRo = srcWMtx.rotation(asQuaternion=True)
        srcWTr = srcWMtx.translation(om2.MSpace.kWorld)

        for i in xrange(self.selList.length() - 1):
            tgtMFnXfo = om2.MFnTransform(self.selList.getDagPath(i))
            tgtDagNode = om2.MFnDagNode(self.selList.getDagPath(i))
            
            tgtTransform = tgtMFnXfo.transformation()
            self.origTransforms.append(tgtTransform)
            
            newTrans = tgtTransform

            if self.matchScale is True:
                newTrans.setScale(srcWSc, om2.MSpace.kWorld)

            if self.matchRotation is True:
                newTrans.setRotation(srcWRo)

            if self.matchTranslation is True:
                newTrans.setTranslation(srcWTr, om2.MSpace.kWorld)

            tgtParentMObj = tgtDagNode.parent(0)
            if tgtParentMObj.hasFn(om2.MFn.kTransform) and self.matchTranslation is True:
                parentDepNode = om2.MFnDependencyNode(tgtParentMObj)
                parentInvMatrixPlug = parentDepNode.findPlug('worldInverseMatrix', False)
                parentInvMatrixPlugEl = parentInvMatrixPlug.elementByLogicalIndex(0)
                parentInvMatrixMObj = parentInvMatrixPlugEl.asMObject()
                parentInvMatrix = om2.MFnMatrixData(parentInvMatrixMObj).matrix()

                newTransMatrix = newTrans.asMatrix()                                
                newMatrix = newTransMatrix * parentInvMatrix
                newTrans = om2.MTransformationMatrix(newMatrix)

            tgtMFnXfo.setTransformation(newTrans)

    def undoIt(self):
        for i in xrange(self.selList.length() - 1):
            tgtMFnXfo = om2.MFnTransform(self.selList.getDagPath(i))
            tgtMFnXfo.setTransformation(self.origTransforms[i])

    def isUndoable(self):
        return True

    # Creator
    @staticmethod
    def creator():
        return ETToolsMatchXfoCmd()

    # Syntax Creator
    @staticmethod
    def syntaxCreator():
        syntax = om2.MSyntax()

        syntax.setObjectType(om2.MSyntax.kSelectionList)
        syntax.useSelectionAsDefault(True)
        
        syntax.addFlag("sc", "scale", om2.MSyntax.kBoolean)
        syntax.addFlag("ro", "rotation", om2.MSyntax.kBoolean)
        syntax.addFlag("tr", "translation", om2.MSyntax.kBoolean)

        return syntax

# ===========
# Menu Setup
# ===========
def setupMenu():
    mainWindow = maya.mel.eval('$tmpVar=$gMainWindow')

    menuName = 'etTools'
    menus = cmds.window(mainWindow, query=True, ma=True)
    if menuName in menus:
        return

    etToolsMenu = cmds.menu(menuName, parent=mainWindow, label=menuName, to=True)

    transformsMenu = cmds.menuItem(parent=etToolsMenu, label="Transforms", sm=True)
    cmds.menuItem(parent=transformsMenu, label="Match Scale",
                  c="cmds.etToolsMatchXfo(rotation=False, translation=False)", stp='python')

    cmds.menuItem(parent=transformsMenu, label="Match Rotation",
                  c="cmds.etToolsMatchXfo(scale=False, translation=False)", stp='python')

    cmds.menuItem(parent=transformsMenu, label="Match Translation",
                  c="cmds.etToolsMatchXfo(scale=False, rotation=False)", stp='python')

    cmds.menuItem(parent=transformsMenu, label="Match All Transforms",
                  c="cmds.etToolsMatchXfo()", stp='python')

def removeMenu():

    if cmds.menu("etTools", query=True, exists=True):
        cmds.deleteUI("etTools", menu=True)

# =======================
# Plug-in Initialization
# =======================
def initializePlugin(mobject):

    cmds.loadPlugin("matrixNodes", quiet=True)
    cmds.pluginInfo('matrixNodes', edit=True, autoload=True)

    mplugin = om2.MFnPlugin(mobject)

    try:
        mplugin.registerCommand('etToolsMatchXfo', ETToolsMatchXfoCmd.creator, ETToolsMatchXfoCmd.syntaxCreator)
    except:
        sys.stderr.write('Failed to register commands: etToolsMatchXfo')
        raise

    setupMenu()

def uninitializePlugin(mobject):

    mplugin = om2.MFnPlugin(mobject)

    removeMenu()

    commandNames = ['etToolsMatchXfo']

    for cmdName in commandNames:
        try:
            mplugin.deregisterCommand(cmdName)
        except:
            sys.stderr.write('Failed to unregister command: {}'.format(cmdName))
