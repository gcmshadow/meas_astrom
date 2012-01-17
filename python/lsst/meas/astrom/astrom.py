import os
import math

import lsst.pex.logging as pexLog
import lsst.pex.config as pexConfig
import lsst.afw.geom as afwGeom
import lsst.meas.algorithms.utils as maUtils
#import lsst.meas.astrom as measAst
import sip as astromSip
import net as astromNet
#import lsst.meas.astrom.sip as astromSip
#from astromSip import cleanBadPoints
#import lsst.meas.astrom.determineWcs as detwcs


# Object returned by determineWcs.
class InitialAstrometry(object):
    def __init__(self):
        self.matches = None
        self.wcs = None
    def getMatches(self):
        return self.matches
    def getWcs(self):
        return self.wcs
    def getMatchMetadata(self):
        return getattr(self, 'matchMetadata', None)

class Astrometry(object):
    import config
    ConfigClass = config.AstromConfig

    def __init__(self,
                 config,
                 #andDir=None,
                 andConfig=None,
                 log=None,
                 logLevel=pexLog.Log.INFO):
        '''
        conf: an AstromConfig object.
        andConfig: an AstromNetDataConfig object
        log: a pexLogging.Log
        logLevel: if log is None, the log level to use
        '''
        self.config = config
        if log is not None:
            self.log = log
        else:
            self.log = pexLog.Log(pexLog.Log.getDefaultLog(),
                                  'meas.astrom',
                                  logLevel)

        if andConfig is not None:
            self.andConfig = andConfig
        else:
            #dirnm = andDir
            #if dirnm is None:
            # ASSUME SETUP IN EUPS
            dirnm = os.environ.get('ASTROMETRY_NET_DATA_DIR')
            if dirnm is None:
                self.log.log(pexLog.Log.WARN, 'astrometry_net_data is not setup')
            else:
                fn = os.path.join(dirnm, 'metadata.paf')
                self.andConfig = pexConfig.Config.load(fn)

    def _debug(self, s):
        self.log.log(self.log.DEBUG, s)
    def _warn(self, s):
        self.log.log(self.log.WARN, s)

    def setAndConfig(self, andconfig):
        self.andConfig = andconfig

    def determineWcs(self,
                     sources,
                     exposure):
        '''
        Version of determineWcs(), meant for pipeline use, that gets
        almost all its parameters from config or reasonable defaults.
        '''
        assert(exposure is not None)
        rdrad = self.config.raDecSearchRadius * afwGeom.degrees
        #filterName = exposure.getFilter().getName()
        #if filterName is None:
        #   filterName = self.andConfig.defaultMagColumn

        return self.determineWcs2(sources, exposure,
                                  searchRadius=rdrad,
                                  #filterName=filterName,
                                  usePixelScale = self.config.useWcsPixelScale,
                                  useRaDecCenter = self.config.useWcsRaDecCenter)
        

    def determineWcs2(self,
                      sources,
                      exposure=None,
                      wcs=None,
                      imageSize=None,
                      radecCenter=None,
                      searchRadius=None,
                      pixelScale=None,
                      filterName=None,
                      doTrim=False,
                      usePixelScale=True,
                      useRaDecCenter=True,
                      searchRadiusScale=2.):
        '''
        We dont really need an Exposure; we need:
          -an initial Wcs estimate;
          -the image size;
          -the filter
        (all of which are metadata of Exposure).

        We also need the estimated pixel scale, which again we can get
        from the initial Wcs, but it should be possible to specify it
        without needing a Wcs.

        Same with the estimated RA,Dec and search radius.

        filterName: string
        imageSize: (W,H) integer tuple/iterable
        pixelScale: afwGeom::Angle per pixel.
        radecCenter: afwCoord::Coord
        '''

        if not useRaDecCenter and radecCenter is not None:
            raise RuntimeError('radecCenter is set, but useRaDecCenter is False.  Make up your mind!')
        #if not useRaDecCenter and searchRadius is not None:
        #    raise RuntimeError('searchRadius is set, but useRaDecCenter is False.  Make up your mind!')
        if not usePixelScale and pixelScale is not None:
            raise RuntimeError('pixelScale is set, but usePixelScale is False.  Make up your mind!')
        
        # return value:
        astrom = InitialAstrometry()
        
        if exposure is not None:
            if filterName is None:
                filterName = exposure.getFilter().getName()
            if imageSize is None:
                imageSize = (exposure.getWidth(), exposure.getHeight())
            if wcs is None:
                wcs = exposure.getWcs()

        if imageSize is None:
            # Could guess from the extent of the Sources...
            raise RuntimeError('Image size must be specified by passing "exposure" or "imageSize"')
        W,H = imageSize
        xc, yc = W/2. + 0.5, H/2. + 0.5
        
        if wcs is not None:
            if pixelScale is None:
                if usePixelScale:
                    pixelScale = wcs.pixelScale()

            if radecCenter is None:
                if useRaDecCenter:
                    radecCenter = wcs.pixelToSky(xc, yc)

            if searchRadius is None:
                if useRaDecCenter:
                    assert(pixelScale is not None)
                    searchRadius = (pixelScale * math.hypot(W,H)/2. *
                                    searchRadiusScale)
                

        if doTrim:
            n = len(sources)
            if exposure is not None:
                bbox = afwGeom.Box2D(exposure.getMaskedImage().getBBox(afwImage.PARENT))
            else:
                # CHECK -- half-pixel issues here?
                bbox = afwGeom.Box2D(afwGeom.Point2D(0.,0.), afwGeom.Point2D(W, H))
            sources = _trimBadPoints(sources, bbox)
            self._debug("Trimming: kept %i of %i sources" % (n, len(sources)))

        '''
        hscAstrom does:
        isSolved, wcs, matchList = runMatch(sourceSet, catSet, min(policy.get('numBrightStars'), len(sourceSet)), log=log)
        '''


        wcs,qa = self._solve(sources, wcs, imageSize, pixelScale, radecCenter, searchRadius)
        pixelMargin = 50.
        cat = self.getReferenceSourcesForWcs(self, wcs, imageSize, filterName,
                                             pixelMargin)

        matchList = self._getMatchList(sources, cat, wcs)

        uniq = set([sm.second.getId() for sm in matchList])
        if len(matchList) != len(uniq):
            self._warn('The list of matched stars contains duplicate reference source IDs (%i sources, %i unique ids)'
                       % (len(matchList), len(uniq)))
        if len(matchList) == 0:
            self._warn('No matches found between input sources and reference catalogue.')
            return astrom

        self._debug('%i reference objects match input sources using linear WCS' % (len(matchList)))

        astrom.tanWcs = wcs
        astrom.tanMatches = matchList

        srcids = [s.getSourceId() for s in sources]
        for m in matchList:
            assert(m.second.getSourceId() in srcids)
            assert(m.second in sources)

        if self.config.calculateSip:
            wcs,matchList = self._calculateSipTerms(wcs, cat, sources)
            astrom.sipWcs = wcs
            astrom.sipMatches = matchList

        # REALLY?
        if exposure is not None:
            exposure.setWcs(wcs)

        meta = createMetadata(W, H, wcs, filterName)
        #matchListMeta = solver.getMatchedIndexMetadata()
        #moreMeta.combine(matchListMeta)

        astrom.matchMetadata = meta
        astrom.wcs = wcs
        astrom.matches = matchList

        return astrom




    #### FIXME!
    def _calculateSipTerms(self, origWcs, cat, sources, matchList):
        '''Iteratively calculate sip distortions and regenerate matchList based on improved wcs'''
        sipOrder = self.config.sipOrder
        wcs = origWcs

        i=0
        while True:
            try:
                sipObject = astromSip.CreateWcsWithSip(matchList, wcs, sipOrder)
                proposedWcs = sipObject.getNewWcs()
            except LsstCppException, e:
                self._warn('Failed to calculate distortion terms. Error: ' + str(e))
                break

            matchSize = len(matchList)
            self._debug('Sip Iteration %i: %i objects match. rms scatter is %g arcsec or %g pixels' %
                        (i, matchSize, sipObject.getScatterOnSky().asArcseconds(), sipObject.getScatterInPixels()))
            # use new WCS to get new matchlist.
            proposedMatchlist = self._getMatchList(sources, cat, proposedWcs)
            if len(proposedMatchlist) <= matchSize:
                # We're regressing, so stop
                break
            wcs = proposedWcs
            matchList = proposedMatchlist
            matchSize = len(matchList)
            i += 1

        return wcs, matchList


    def _getMatchList(self, sources, cat, wcs):
        dist = self.config.catalogMatchDist * afwGeom.arcseconds
        clean = self.cleaningParameter
        matcher = astromSip.MatchSrcToCatalogue(cat, img, wcs, dist)
        matchList = matcher.getMatches()
        if matchList is None:
            raise RuntimeError('No matches found between image and catalogue')
        matchList = astromSip.cleanBadPoints.clean(matchList, wcs, nsigma=clean)
        return matchList



    def _mapFilterName(self, filterName, default=None):
        ## Warn if default is used?
        return self.andConfig.mapColumnMap.get(filterName, default)

    def getReferenceSourcesForWcs(self, wcs, imageSize, filterName, pixelMargin,
                                  trim=True):
        rdc = wcs.pixelToSky(xc, yc)
        pixelScale = wcs.pixelScale()
        rad = pixelScale * (math.hypot(W,H)/2. + pixelMargin)
        cat = self.getReferenceSources(rdc.getRa(), rdc.getDec(),
                                       rad, filterName)
        # apply WCS to set x,y positions
        for s in cat:
            s.setAllXyFromRaDec(wcs)
        if trim:
            # cut to image bounds + margin.
            bbox = afwGeom.Box2D(afwGeom.Point2D(0.,0.), afwGeom.Point2D(W, H))
            bbox.grow(pixelMargin)
            cat = _trimBadPoints(cat, bbox)
        return cat
        

    def getReferenceSources(self, ra, dec, radius, filterName):
        '''
        Returns: list of Source objects.
        '''
        solver = self._getSolver()
        magcolumn = self._mapFilterName(filterName, self.andConfig.defaultMagColumn)
        refcat = solver.getCatalogue(ra, dec, radius, filterName,
                                     magcolumn,
                                     self.andConfig.idColumn,
                                     -1, False, True, True);
        # magic values:
        # int indexId = -1,
        # bool useIndexHealpix = true,
        # bool resolveDuplicates = true,
        # bool resolveUsingId = true

        # Now add the photometric errors, star/galaxy, and variability flags.
        sgCol = self.andConfig.starGalaxyColumn
        varCol = self.andConfig.variableColumn
        magerrCol = self.andConfig.magErrorColumnMap.get(filterName, None)

        cols = solver.getTagAlongColumns()
        colnames = [c.name for c in cols]
        irefs = refcat.intrefsources
        cat = refcat.refsources

        if sgCol is None:
            stargal = None
        else:
            assert(sgCol in colnames)
            stargal = solver.getTagAlongBool(irefs, sgCol)

        if varCol is None:
            variable = None
        else:
            assert(varCol in colnames)
            variable = solver.getTagAlongBool(irefs, varCol)

        if magerrCol is None:
            magerr = None
        else:
            assert(magerrCol in colnames)
            magerr = solver.getTagAlongDouble(irefs, magerrCol)

        # set STAR flag
        fdict = maUtils.getDetectionFlags()
        starflag = fdict["STAR"]
        if stargal is not None:
            assert(len(stargal) == len(cat))
        if variable is not None:
            assert(len(variable) == len(cat))

        for i in xrange(len(cat)):
            isstar = True
            if stargal is not None:
                isstar &= stargal[i]
            if variable is not None:
                isstar &= not(variable[i])
            if isstar:
                cat[i].setFlagForDetection(cat[i].getFlagForDetection() | starflag)

        # set flux error based on magnitude error
        if magerr is not None:
            assert(len(magerr) == len(cat))
            for i in xrange(len(cat)):
                cat[i].setPsfFluxErr(magerr[i] * cat[i].getPsfFlux() * -numpy.log(10.)/2.5)

        return cat
                                          
        


    def _solve(self, sources, wcs, imageSize, pixelScale, radecCenter,
               searchRadius):
        solver = self._getSolver()

        # FIXME -- select sources with valid x,y,flux?
        print 'Sources:', sources
        solver.setStars(sources)
        solver.setMaxStars(self.config.maxStars)
        solver.setImageSize(*imageSize)
        if radecCenter is not None:
            ra = radecCenter.getRa().asDegrees()
            dec = radecCenter.getDec().asDegrees()
            solver.setRaDecRadius(ra, dec, searchRadius.asDegrees())

        # FIXME
        # matchThreshold
        # parity

        import astrometry_net as an
        an.an_log_set_level(3)

        print 'pixelScale:', pixelScale
        if pixelScale is not None:
            dscale = self.config.pixelScaleUncertainty
            scale = pixelScale.asArcseconds()
            lo = scale / dscale
            hi = scale * dscale
            #solver.setPixelScaleRange(lo, hi)
            print 'Setting pixel scale range', lo, hi
            solver.funits_lower = lo
            solver.funits_upper = hi
        else:
            solver.funits_lower = 0.01
            solver.funits_upper = 3600.

        (W,H) = imageSize
        hi = math.hypot(W,H)
        lo = 0.1 * min(W,H)
        print 'Setting quad size range:', lo, hi
        an.solver_set_quad_size_range(solver, lo, hi)

        ## AN 0.30
        if True:
            solver.logratio_record_threshold = self.config.matchThreshold
        else:
            # an.solver_set_keep_logodds(solver, self.config.matchThreshold)
            # solver.logratio_tokeep = self.config.matchThreshold
            pass
        '''
        _mylog.format(pexLog::Log::DEBUG, "Exposure\'s WCS scale: %g arcsec/pix; setting scale range %.3f - %.3f arcsec/pixel",
        pixelScale.asArcseconds(), lwr.asArcseconds(), upr.asArcseconds());
        '''
        #if ( wcsPtr->isFlipped()) {
        #setParity(FLIPPED_PARITY);
        #setParity(NORMAL_PARITY);

        for fn in self.andConfig.indexFiles:
            print 'Adding index file', fn
            fn = self._getIndexPath(fn)
            print 'Path', fn
            #ind = an.index_load(fn)
            solver.addIndex(fn)

        an.solver_log_params(solver)
        #an.solver_print_to(solver, 
        
        solver.run()
        if solver.didSolve():
            print 'Solved!'
            wcs = solver.getWcs()
            print 'Got wcs:', wcs
            
        else:
            print 'Did not solve.'
            wcs = None
        ### FIXME!
        #args = []
        #if wcs is not None:
        #    args.append(wcs)
        #    if pixelScale is not None:
        #        args.append

        #...
        return wcs,None

    def _getIndexPath(self, fn):
        if os.path.isabs(fn):
            return fn
        andir = os.getenv('ASTROMETRY_NET_DATA_DIR')
        if andir is not None:
            fn2 = os.path.join(andir, fn)
            if os.path.exists(fn2):
                return fn2
        fn2 = os.path.abspath(fn)
        return fn2
                    


    def _getSolver(self):
        #solver = astromNet.GlobalAstrometrySolution(path, log)
        import astrometry_net as an
        _solver = an.solver_new()
        print 'Solver:', _solver
        #print 'dir:', dir(_solver)
        return _solver

    @staticmethod
    def _trimBadPoints(sources, bbox):
        '''Remove elements from sourceSet whose xy positions are not within the given bbox.

        sources:  an iterable of Source objects
        bbox: an afwImage.Box2D
        
        Returns:
        a list of Source objects with xAstrom,yAstrom within the bbox.
        '''
        keep = []
        for s in sources:
            if bbox.contains(afwGeom.Point2D(s.getXAstrom(), s.getYAstrom())):
                keep.append(s)
        return keep


def _createMetadata(width, height, wcs, filterName):
    """
    Create match metadata entries required for regenerating the catalog

    @param width Width of the image (pixels)
    @param height Height of the image (pixels)
    @param filterName Name of filter, used for magnitudes
    @return Metadata
    """
    meta = dafBase.PropertyList()

    #andata = os.environ.get('ASTROMETRY_NET_DATA_DIR')
    #if andata is None:
    #    meta.add('ANEUPS', 'none', 'ASTROMETRY_NET_DATA_DIR')
    #else:
    #    andata = os.path.basename(andata)
    #    meta.add('ANEUPS', andata, 'ASTROMETRY_NET_DATA_DIR')

    # cache: field center and size.  These may be off by 1/2 or 1 or 3/2 pixels.
    cx,cy = 0.5 + width/2., 0.5 + height/2.
    radec = wcs.pixelToSky(cx, cy).toIcrs()
    meta.add('RA', radec.getRa().asDegrees(), 'field center in degrees')
    meta.add('DEC', radec.getDec().asDegrees(), 'field center in degrees')
    imgSize = wcs.pixelScale() * hypot(width, height)/2.
    meta.add('RADIUS', imgSize.asDegrees(),
             'field radius in degrees, approximate')
    meta.add('SMATCHV', 1, 'SourceMatchVector version number')
    meta.add('FILTER', filterName, 'LSST filter name for tagalong data')
    #meta.add('STARGAL', stargalName, 'star/galaxy name for tagalong data')
    #meta.add('VARIABLE', variableName, 'variability name for tagalong data')
    #meta.add('MAGERR', magerrName, 'magnitude error name for tagalong data')
    return meta
