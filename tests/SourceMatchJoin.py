#!/usr/bin/env python

import os, sys
from math import *
import unittest
import eups
import random
import lsst.utils.tests as utilsTests
import lsst.daf.base as dafBase
import lsst.daf.persistence as dafPersist
import lsst.pex.exceptions as pexExceptions
import lsst.pex.logging as logging
import lsst.pex.policy as policy
import lsst.afw.geom as afwGeom
import lsst.afw.image as afwImage
import lsst.afw.detection as afwDet
import lsst.afw.math as afwMath
import lsst.afw.display.ds9 as ds9
import lsst.afw.display.utils as displayUtils
import lsst
import lsst.meas.astrom as measAstrom
from lsst.pex.logging import Log

try:
    type(verbose)
except NameError:
    display = False
    verbose = 0

def roundTripSourceMatch(storagetype, filename, matchlist):
    pol = policy.Policy()
    additionalData = dafBase.PropertySet()

    loc = dafPersist.LogicalLocation(filename)
    persistence = dafPersist.Persistence.getPersistence(pol)
    storageList = dafPersist.StorageList()
    storage = persistence.getPersistStorage(storagetype, loc)
    storageList.append(storage)
    persistence.persist(matchlist, storageList, additionalData)

    storageList2 = dafPersist.StorageList()
    storage2 = persistence.getRetrieveStorage(storagetype, loc)
    storageList2.append(storage2)
    matchlistptr = persistence.unsafeRetrieve("PersistableSourceMatchVector", storageList2, additionalData)
    matchlist2 = afwDet.PersistableSourceMatchVector.swigConvert(matchlistptr)

    return matchlist2

class matchlistTestCase(unittest.TestCase):
    def setUp(self):
        pass
    def tearDown(self):
        pass

    def testJoin(self):
        pol = policy.Policy()
        pol.set('matchThreshold', 30)
        log = Log.getDefaultLog()

        ra,dec,rad = 2.389, 3.287, 0.158
        filtername,idname = 'r','id'
        anindid = 101109003

        solver = measAstrom.createSolver(pol, log)
        ss = solver.getCatalogue(ra, dec, rad*3600., filtername, idname, anindid)
        print 'got', len(ss), 'catalog sources'

        smv = afwDet.SourceMatchVector()
        for i,s1 in enumerate(ss):
            sm = afwDet.SourceMatch()
            sm.first = s1
            s2 = afwDet.Source()
            s2.setSourceId(1000 + i)
            sm.second = s2
            sm.distance = 0
            smv.push_back(sm)

        psmv = afwDet.PersistableSourceMatchVector(smv)

        extra = dafBase.PropertyList()
        # as in meas_astrom : determineWcs.py
        andata = os.environ.get('ASTROMETRY_NET_DATA_DIR')
        if andata is None:
            extra.add('ANEUPS', 'none', 'ASTROMETRY_NET_DATA_DIR')
        else:
            andata = os.path.basename(andata)
            extra.add('ANEUPS', andata, 'ASTROMETRY_NET_DATA_DIR')
        anindfn = '/home/dalang/lsst/astrometry_net_data/imsim-2010-11-09-0/index-101109003.fits'
        extra.add('RA', ra)
        extra.add('DEC', dec)
        extra.add('RADIUS', rad)
        extra.add('ANINDNM', anindfn)
        extra.add('ANINDID', anindid)
        extra.add('ANINDHP', -1)
        extra.add('SMATCHV', 1)

        psmv.setSourceMatchMetadata(extra)

        psmv2 = roundTripSourceMatch('FitsStorage', 'tests/data/matchlist.fits', psmv)
        smv2 = psmv2.getSourceMatches()
        extra2 = psmv2.getSourceMatchMetadata()

        print 'Got SMV:', smv2
        print 'Got metadata:', extra2
        print extra2.toString()

        measAstrom.joinMatchListWithCatalog(smv2, extra2, pol, filterName=filtername, idName=idname)

        self.assertEqual(len(smv2), len(smv))
        for i in xrange(len(smv)):
            self.assertEqual(smv2[i].first.getSourceId(), smv[i].first.getSourceId())
            self.assertEqual(smv2[i].second.getSourceId(), smv[i].second.getSourceId())
            self.assertEqual(smv2[i].first.getRa(), smv[i].first.getRa())
            self.assertEqual(smv2[i].first.getDec(), smv[i].first.getDec())
            self.assertEqual(smv2[i].first.getPsfFlux(), smv[i].first.getPsfFlux())


            
#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-= silly boilerplate -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-

def suite():
    utilsTests.init()
    suites = []
    suites += unittest.makeSuite(matchlistTestCase)
    suites += unittest.makeSuite(utilsTests.MemoryTestCase)
    return unittest.TestSuite(suites)

def run(exit=False):
    """Run the utilsTests"""
    utilsTests.run(suite(), exit)

if __name__ == "__main__":
    run(True)