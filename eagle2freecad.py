#################################################################################
#This is licenced under CC-BY-NC (http://creativecommons.org/licenses/by-nc/2.0/)
#Please contact Christian Aurich for commercial use of this software.
#http://c-aurich.de
#################################################################################

import Part
from FreeCAD import Base
import csv
import FreeCAD, FreeCADGui, Part
import math
from PyQt4 import QtGui
from PyQt4 import QtCore
import os
import string

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

def getAngle(x1,y1,x2,y2):
  x_diff = x2-x1
  y_diff = y2-y1
  
  if x_diff != 0:
    angle = math.degrees(math.atan(y_diff / x_diff))
  else:
    angle = 90
  
  if (x2 < x1):
    angle += 180
  elif (x2==x1 and y2<y1):
    angle += 180
  
  return angle

def getCurvedLine(x1,y1,x2,y2,curve):
  #middle between start and end point
  x_mid = (x1 + x2) / 2
  y_mid = (y1 + y2) / 2
  
  #difference between the points to calculate the angle of the direct line
  angle = getAngle(x1,y1,x2,y2)
  
  
  #add angle between mid and center points which is 90 degrees
  angle += 90
  
  #distance from point 1 to the middle point
  dist_1_mid = ((x1-x_mid)**2 + (y1-y_mid)**2)**0.5
  
  #distance from the middle point to the center of the circle
  dist_mid_center = dist_1_mid / math.tan(math.radians(curve/2))
    
  x_center = x_mid + dist_mid_center * math.cos(math.radians(angle))
  y_center = y_mid + dist_mid_center * math.sin(math.radians(angle))

  radius = ( (x_center - x1)**2 + (y_center - y1)**2)**0.5
  
  #get angle from center to middle point
  angle = getAngle(x_center, y_center, x_mid, y_mid)
  #point 3 that is the last missing point to draw an arc
  x3 = x_center + radius * math.cos(math.radians(angle))
  y3 = y_center + radius * math.sin(math.radians(angle))
  
  arc = Part.Arc(Base.Vector(x1,y1,0),Base.Vector(x3,y3,0),Base.Vector(x2,y2,0))
  return arc

def getLine(elem):
  if ('curve' not in elem):
    return Part.makeLine((elem.attrib['x1'], elem.attrib['y1'],0), (elem.attrib['x2'],elem.attrib['y2'],0))
  else:
    return getCurvedLine(elem.attrib['x1'], elem.attrib['y1'],elem.attrib['x2'], elem.attrib['y2'], elem.attrib['curve'])

def getEdgeByParams(x1,y1,x2,y2,curve):
  if (curve == 0):
    return Part.makeLine((x1, y1,0), (x2,y2,0))
  else:
    return Part.Edge(getCurvedLine(x1, y1,x2, y2, curve))


def getPlacedModel(part, model,height):
    if 'rot' in part.attrib:
      rot = float(part.attrib['rot'].translate(None, string.letters))
      mirror = part.attrib['rot'].translate(None, string.digits)
    else:
      rot = 0
      mirror='R'
    p = model.copy()
    p.translate(Base.Vector(0,0,height / 2))

    p.rotate(Base.Vector(0,0,0),Base.Vector(0,0,1),-rot)
    mirrorMultiplicator = 1
    if (mirror[0] == 'M'):
      p.rotate(Base.Vector(0,0,0), Base.Vector(0,1,0), 180)
      mirrorMultiplicator = -1
    p.translate(Base.Vector(float(part.attrib['x']),float(part.attrib['y']),0))
    return p

def getWireFromPolygon(elem):
  millwire = []
  lastPoint = ''
  firstPoint = ''
  curve = 0
  for elem2 in elem.iterfind('vertex'):
    nextPoint = Base.Vector(float(elem2.attrib['x']),float(elem2.attrib['y']),0)
    if (lastPoint == ''):
      firstPoint = nextPoint
    else:
      millwire.append(getEdgeByParams(lastPoint[0], lastPoint[1], nextPoint[0], nextPoint[1], curve))
    curve = 0
    if 'curve' in elem2.attrib:
      curve = float(elem2.attrib['curve'])

    lastPoint = nextPoint
  millwire.append(getEdgeByParams(lastPoint[0], lastPoint[1], firstPoint[0], firstPoint[1], curve))
    
  return Part.Wire(millwire)

libFolder = ''
filename = ''
libFolder = str(QtGui.QFileDialog.getExistingDirectory(None, "Select Directory for Libraries"))
filename = str(QtGui.QFileDialog.getOpenFileName(None, 'Open Eagle Board file',''))


holes = []
parts = []
edges = []
PCBs = []
milling = []
packages = {}
missingpackages = {}

milledVolumes = []

tree = ET.ElementTree(file=filename)
root = tree.getroot()
drawing = root[0]
dimensionLibrary = {}
drillLibrary = {}
millingLibrary = {}
milledVolumesLibrary = {}


#get total Height of PCB
totalHeight = 0
layerThicknesses = drawing.find('board/designrules/param[@name="mtCopper"]').attrib['value']
layerThicknesses = layerThicknesses.translate(None, string.letters).split(' ')

layerSpacings    = drawing.find('board/designrules/param[@name="mtIsolate"]').attrib['value']
layerSpacings    = layerSpacings.translate(None, string.letters).split(' ')

layerSetup       = drawing.find('board/designrules/param[@name="layerSetup"]').attrib['value']
layerSetup       = layerSetup.replace('*',' ').replace('+',' ')
layerSetup       = layerSetup.replace('(', ' ').replace(')',' ')
layerSetup       = layerSetup.replace('[', ' ').replace(']',' ').strip().split(' ')

lastLayer        = -1
for layer in layerSetup:
  print "Layer: ", layer
  print "adding thickness of layer: ", layerThicknesses[int(layer)-1]
  totalHeight += float(layerThicknesses[int(layer)-1])
  if (lastLayer >= 0):
    print "adding thickness of spacing: ", layerSpacings[int(lastLayer)-1]
    totalHeight += float(layerSpacings[int(lastLayer)-1])
  lastLayer = layer

#find lines that make up the dimensions of pcbs directly
for elem in drawing.iterfind('board/plain/wire[@layer="20"]'):
  tmpedge = Part.makeLine((elem.attrib['x1'],elem.attrib['y1'],0), (elem.attrib['x2'],elem.attrib['y2'],0))
  edges.append(tmpedge);

#find lines that make up the milling of pcbs directly
for elem in drawing.iterfind('board/plain/wire[@layer="46"]'):
  tmpedge = Part.makeLine((elem.attrib['x1'],elem.attrib['y1'],0), (elem.attrib['x2'],elem.attrib['y2'],0))
  milling.append(tmpedge);

#find parts that contain dimension lines or holes or millings
for elem in drawing.iterfind('board/libraries/library'):
  library = elem.attrib['name']
  for elem2 in elem.iterfind('packages/package'):
    part = elem2.attrib['name']
    for elem3 in elem2.iterfind('wire[@layer="20"]'):
      if library not in dimensionLibrary:
        dimensionLibrary[library] = {}
      if part not in dimensionLibrary[library]:
        dimensionLibrary[library][part] = []
      dimensionLibrary[library][part].append(getLine(elem3))
    for elem3 in elem2.iterfind('wire[@layer="46"]'):
      if library not in millingLibrary:
        millingLibrary[library] = {}
      if part not in millingLibrary[library]:
        millingLibrary[library][part] = []
      millingLibrary[library][part].append(getLine(elem3))
    for elem3 in elem2.iterfind('hole'):
      if library not in drillLibrary:
        drillLibrary[library] = {}
      if part not in drillLibrary[library]:
        drillLibrary[library][part] = []
      drillLibrary[library][part].append(Part.makeCylinder(float(elem3.attrib['drill']),totalHeight,Base.Vector(float(elem3.attrib['x']),float(elem3.attrib['y']),-totalHeight/2)))
    for elem3 in elem2.iterfind('polygon[@layer="46"]'):
      if library not in milledVolumesLibrary:
        milledVolumesLibrary[library] = {}
      if part not in milledVolumesLibrary[library]:
        milledVolumesLibrary[library][part] = []
      millwire = getWireFromPolygon(elem3)
      millwire = Part.Face(millwire)
      millwire.translate(Base.Vector(0,0,-totalHeight/2))
      milledVolumesLibrary[library][part].append(millwire.extrude(Base.Vector(0,0,totalHeight)))



for elem in drawing.iterfind('board/elements/element'):
  #use parts from library to finish list of dimensions
  if elem.attrib['library'] in dimensionLibrary and elem.attrib['package'] in dimensionLibrary[elem.attrib['library']]:
    for elem2 in dimensionLibrary[elem.attrib['library']][elem.attrib['package']]:
      dimensionLineCpy = getPlacedModel(elem, elem2,0)
      edges.append(dimensionLineCpy)
  #use parts from library to finish list of millings
  if elem.attrib['library'] in millingLibrary and elem.attrib['package'] in millingLibrary[elem.attrib['library']]:
    for elem2 in millingLibrary[elem.attrib['library']][elem.attrib['package']]:
      millingLineCpy = getPlacedModel(elem, elem2,0)
      milling.append(millingLineCpy)
  if elem.attrib['library'] in milledVolumesLibrary and elem.attrib['package'] in milledVolumesLibrary[elem.attrib['library']]:
    for elem2 in milledVolumesLibrary[elem.attrib['library']][elem.attrib['package']]:
      milledVolume = getPlacedModel(elem, elem2,0)
      milledVolumes.append(milledVolume)
  
  #collect used footprints
  footprint = elem.attrib['package']
  for attribute in elem.iterfind('attribute[@name="STEP"]'):
    footprint = attribute.attrib['value']
  packages[footprint] = ''

#look for files with ending .stp or .step and import the models
#if the packages are used on the pcb
#TODO: add support for importing more than step models (freecad supports more natively)
for dirname, dirnames, filenames in os.walk(libFolder):
  for filename in filenames:
      file = filename.split('.') #attention: files might have more than one dot in their name
      if (file[len(file)-1]=='stp' or file[len(file)-1]=='step'):
        ending = file.pop(len(file)-1) #remove fileending (.stp or .step)
        file = ".".join(file)
        if (file in packages):
          packages[file] = Part.read(os.path.join(dirname, filename))


#insert parts in drawing using the already imported packages
for elem in drawing.iterfind('board/elements/element'):
  footprint = elem.attrib['package']
  for attribute in elem.iterfind('attribute[@name="STEP"]'):
    footprint = attribute.attrib['value']
  if (packages[footprint] == '' and footprint not in missingpackages):
    print "missing package ", footprint
    missingpackages[footprint] = 'reported'
  elif packages[footprint] != '':
    p = getPlacedModel(elem, packages[footprint], totalHeight)
    parts.append(p)


#sort edges to form a single closed 2D shape
#TODO: print a meaningfull error if shapes are found that are not closed
newEdges = [];
newEdges.append(edges.pop(0))
nextCoordinate = newEdges[0].Curve.EndPoint
firstCoordinate = newEdges[0].Curve.StartPoint
while(len(edges)>0):
  print "nextCoordinate: ", nextCoordinate
  for j, edge in enumerate(edges):
    print "compare to: ", edges[j].Curve.StartPoint, "/" , edges[j].Curve.EndPoint
    if edges[j].Curve.StartPoint == nextCoordinate:
      nextCoordinate = edges[j].Curve.EndPoint
      newEdges.append(edges.pop(j))
      break
    elif edges[j].Curve.EndPoint == nextCoordinate:
      nextCoordinate = edges[j].Curve.StartPoint
      newEdges.append(edges.pop(j))
      break
  if nextCoordinate == firstCoordinate:
    newEdges = Part.Wire(newEdges)
    newEdges = Part.Face(newEdges)
    newEdges.translate(Base.Vector(0,0,-totalHeight/2))
    newEdges = newEdges.extrude(Base.Vector(0,0,totalHeight))
    PCBs.append(newEdges)
    newEdges = [];
    newEdges.append(edges.pop(0))
    nextCoordinate = newEdges[0].Curve.EndPoint
    firstCoordinate = newEdges[0].Curve.StartPoint




#sort millings to form a single closed 2D shape
newMilling = [];
newMilling.append(milling.pop(0))
nextCoordinate = newMilling[0].Curve.EndPoint
firstCoordinate = newMilling[0].Curve.StartPoint
while(len(milling)>0):
  print "nextCoordinate: ", nextCoordinate
  for j, edge in enumerate(milling):
    print "compare to: ", milling[j].Curve.StartPoint, "/" , milling[j].Curve.EndPoint
    if milling[j].Curve.StartPoint == nextCoordinate:
      nextCoordinate = milling[j].Curve.EndPoint
      newMilling.append(milling.pop(j))
    elif milling[j].Curve.EndPoint == nextCoordinate:
      nextCoordinate = milling[j].Curve.StartPoint
      newMilling.append(milling.pop(j))
  if nextCoordinate == firstCoordinate:
    newMilling = Part.Wire(newMilling)
    newMilling = Part.Face(newMilling)
    newMilling.translate(Base.Vector(0,0,-totalHeight/2))
    milledVolumes.append(newMilling.extrude(Base.Vector(0,0,totalHeight)))
    newMilling = [];
    newMilling.append(milling.pop(0))
    nextCoordinate = newMilling[0].Curve.EndPoint
    firstCoordinate = newMilling[0].Curve.StartPoint


for extruded in PCBs:
  #search for orientation of each pcb in 3d space, save it (no transformation yet!)
  angle = 0;
  axis = Base.Vector(0,0,1)
  position = Base.Vector(0,0,0)
  
  for elem in drawing.iterfind('board/plain/text[@layer="100"]'):
    if extruded.isInside(Base.Vector(float(elem.attrib['x']),float(elem.attrib['y']),0), 0.000001, True):
      print "found $text"
      keyValue = elem.text.split('=')
      if keyValue[0] == "angle":
        angle = float(keyValue[1])
        print "found angle"
      if keyValue[0] == "axis":
        splitValue = keyValue[1].split(',')
        axis = Base.Vector(float(splitValue[0]),float(splitValue[1]),float(splitValue[2]))
        print "found axis"
      if keyValue[0] == "position":
        splitValue = keyValue[1].split(',')
        position = Base.Vector(float(splitValue[0]),float(splitValue[1]),float(splitValue[2]))
        print "found position"
  
  #remove milled areas of the pcb
  for milledVolume in milledVolumes:
    extruded = extruded.cut(milledVolume)

  #cut out all drilled holes
  for hole in holes:
    extruded = extruded.cut(hole)

  #combine pcb and part if the part is on this pcb
  for part in parts:
    if extruded.isInside(part.Placement.Base, 0.000001, True):
      extruded = extruded.fuse(part)

  #now when the pcb if fully populated perform transformations to align it correctly in 3d space
  extruded.rotate(Base.Vector(0,0,0), axis, angle)
  extruded.translate(position)
  #display the part
  Part.show(extruded)

#filename = str(QtGui.QFileDialog.getSaveFileName(None, 'SAVE as STEP Model',''))
#extruded.exportStep(filename)

