

#include "lsst/meas/astrom/sip/MatchSrcToCatalogue.h"


namespace except = lsst::pex::exceptions;
namespace afwImg = lsst::afw::image;
using namespace lsst::meas::astrom::sip;

MatchSrcToCatalogue::MatchSrcToCatalogue(const det::SourceSet &catSet,  ///<Input list of objects from catalogue
                                         const det::SourceSet &imgSet, ///<Input list of objects from image
                                         const lsst::afw::image::Wcs wcs,   ///< World Coordinate System object
                                         double distInArcsec  ///<Max distance for legal match
                                        )
{
    setImgSrcSet(imgSet);
    setCatSrcSet(catSet);
    setDist(distInArcsec);
    setWcs(wcs);

    findMatches();
}


MatchSrcToCatalogue::~MatchSrcToCatalogue() {
}
    

/// Set a new value for the maximum allowed distance between two matching objects (in ra/dec space) 
void MatchSrcToCatalogue::setDist(double distInArcsec)
{
    if(distInArcsec <= 0){
        throw LSST_EXCEPT(except::InvalidParameterException, "Distance must be > 0");
    }

    _distInArcsec = distInArcsec;
}



/// Set a different Wcs solution
void MatchSrcToCatalogue::setWcs(const lsst::afw::image::Wcs &wcs){
    _wcs = wcs;  //Shallow copy
}

//void MatchSrcToCatalogue::setCatSrcSet(const det::SourceSet &srcSet);

/// Perform a deep copy of a set of sources from the image into this object
///
/// sourceSet is a vector of pointers to Sources. We create deep copies of the objects
/// pointed to so that we can freely mutate them inside the object without affecting
/// the input argument.
void MatchSrcToCatalogue::setImgSrcSet(const det::SourceSet &srcSet) {
    //Destroy the old imgSet
    //imgSet.~imgSet();
    _imgSet = _deepCopySourceSet(srcSet);
}

void MatchSrcToCatalogue::setCatSrcSet(const det::SourceSet &srcSet) {
    _catSet = _deepCopySourceSet(srcSet);
}

void MatchSrcToCatalogue::findMatches() {

    ///@todo Make sure everything is setup as it should be
    //The design of this class ensures all private variables must be set at this point,
    //so assertions should be thrown if this is not the case
    
    //Calculate ra and dec for every imgSrc
    for(unsigned int i=0; i< _imgSet.size(); ++i) {
        double x = _imgSet[i]->getXAstrom();
        double y = _imgSet[i]->getYAstrom();
        
        afwImg::PointD raDec = _wcs.xyToRaDec(x, y);

        _imgSet[i]->setRa(raDec[0]);
        _imgSet[i]->setDec(raDec[1]);
    }
    
    _match = det::matchRaDec(_imgSet, _catSet, _distInArcsec);

      _removeOneToMany();  
      _removeManyToOne();  
                
    if(_match.size() == 0) {
        std::cout << _imgSet.size() << " " << _catSet.size() << std::endl;
        throw LSST_EXCEPT(except::RuntimeErrorException, "No matching objects found");
    }
}


///We require that out matches be one to one, i.e any element matches no more than once for either 
///the catalogue or the image. However, our implementation of findMatches uses det::matchRaDec()
///which does not garauntee that. This function does the (slow) search and removal.
///if @c tupleElement is 0 then one-to-many matches are removed, 1 means many-to-one matches are removed
void MatchSrcToCatalogue::_removeOneToMany() {

    
    unsigned int size = _match.size();
    for(unsigned int i=0; i< size; ++i) {
        for(unsigned int j=i+1; j< size; ++j) {
            //If the same Source appears twice keep the one with the smaller separation from its match
            if( boost::tuples::get<0>(_match[i]) == boost::tuples::get<0>(_match[j]) ) {
                //Keep the one with the shorter match distance, and disgard the other
                if( boost::tuples::get<2>(_match[i]) < boost::tuples::get<2>(_match[j]) ){
                    _match.erase(_match.begin()+j);
                    size--;
                }
                else {  
                    _match.erase(_match.begin()+i);
                    size--;
                    i--;    //Otherwise the for loop will skip an element
                    j = size+1; //Nothing else to do for the deleted element
                }
            }
        }
    }
}


///Yes this is stupid repetition, but boost::tuples are stupid. This function is identical to
///_removeOneToMany() except boost::tuples::get<0> replaced with boost::tuples::get<1>
void MatchSrcToCatalogue::_removeManyToOne() {

    
    unsigned int size = _match.size();
    for(unsigned int i=0; i< size; ++i) {
        for(unsigned int j=i+1; j< size; ++j) {
            //If the same Source appears twice
            if( boost::tuples::get<1>(_match[i]) == boost::tuples::get<1>(_match[j]) ) {
                //Keep the one with the shorter match distance, and disgard the other
                if( boost::tuples::get<2>(_match[i]) < boost::tuples::get<2>(_match[j]) ){
                    _match.erase(_match.begin()+j);
                    size--;
                }
                else {  
                    _match.erase(_match.begin()+i);
                    size--;
                    i--;    //Otherwise the for loop will skip an element
                    j = size+1; //Nothing else to do for the deleted element
                }
            }
        }
    }
}


std::vector<det::SourceMatch> MatchSrcToCatalogue::getMatches() {
    return _match;
}
    

det::SourceSet MatchSrcToCatalogue::_deepCopySourceSet(const det::SourceSet &in) {

    unsigned int size = in.size();
    det::SourceSet out;

    for(unsigned int i=0; i<size; ++i){
        //Allocate heap memory for a new object, pointed to by tmp
        det::Source::Ptr tmp(new det::Source);
        //Deep copy the ith Source
        (*tmp) = *(in[i]);
        out.push_back(tmp);
    }

    return out;
}
        
    
