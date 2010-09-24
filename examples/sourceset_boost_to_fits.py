import sys
from optparse import OptionParser

import lsst.pex.policy                   as pexPolicy
import lsst.daf.persistence              as dafPersist
import lsst.daf.base                     as dafBase
import lsst.afw.detection                as afwDet

from astrometry.util.pyfits_utils import *
from numpy import array

def sourceset_read_boost(fn):
    loc = dafPersist.LogicalLocation(fn)
    storageList = dafPersist.StorageList()
    additionalData = dafBase.PropertySet()
    persistence = dafPersist.Persistence.getPersistence(pexPolicy.Policy())
    storageList.append(persistence.getRetrieveStorage("BoostStorage", loc))
    psvptr = persistence.unsafeRetrieve("PersistableSourceVector", storageList, additionalData)
    psv = afwDet.PersistableSourceVector.swigConvert(psvptr)
    return psv.getSources()

 
if __name__ == '__main__':
    parser = OptionParser(usage='%prog <input.boost> <output.fits>')
    opt,args = parser.parse_args()
    if len(args) != 2:
        parser.print_help()
        sys.exit(-1)
    infn = args[0]
    outfn = args[1]

    ss = sourceset_read_boost(infn)
    print 'Read %i sources from %s' % (len(ss), infn)
    # Find all methods in Source called "getXXX".  Create columns in the FITS
    # table called "XXX".
    sfuncs = dir(ss[0])
    sfuncs.sort()
    fields = [(g, g[3:]) for g in sfuncs if g.startswith('get')]
    out = tabledata()
    for getterName,name in fields:
        out.set(name, array([getattr(s, getterName)() for s in ss]))
    print 'Writing %i columns to %s' % (len(out.columns()), outfn)
    out.writeto(outfn)

        