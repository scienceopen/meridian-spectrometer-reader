from pathlib import Path
import logging
from typing import Optional, List
from netCDF4 import Dataset
from xarray import DataArray
from numpy import arange, array
from datetime import datetime, timedelta
from dateutil.parser import parse
import sciencedates as sd


def readmsp(fn: Path, tlim: List[datetime]=None, elim: tuple=None) -> DataArray:
    """
    This function works with 1983-2010 netCDF3 as well as 2011-present netCDF4 files.
    """
    fn = Path(fn).expanduser()
# %% date from filename -- only way
    ext = fn.suffix.lower()
    if ext == '.nc':
        d0 = sd.forceutc(datetime.strptime(fn.stem[13:21], '%Y%m%d'))
    elif ext == '.pf':
        d0 = sd.yeardoy2datetime(int(fn.stem[4:]))

    with Dataset(fn, 'r') as f:
        # %% load by time
        secdayutc = f['Time'][:]
        # convert to datetimes -- need as ndarray for next line
        t = array([d0 + timedelta(seconds=int(s)) for s in secdayutc])
        if tlim is not None and len(tlim) == 2:
            if isinstance(tlim[0], str):
                tlim = [parse(t) for t in tlim]
            tind = (tlim[0] <= t) & (t <= tlim[1])
        else:
            tind = slice(None)
# %% elevation from North horizon
        elv = arange(181.)
        if elim is not None and len(elim) == 2:
            elind = (elim[0] <= elv) & (elv <= elim[1])
        else:
            elind = slice(None)
# %% wavelength channels
        """
        We use integer Angstrom because single float records cause difficulty with index by float
        """
        wavelen = (f['Wavelength'][:] * 10).astype(int)
        goodwl = wavelen > 1.  # some channels are unused in some files
# %% load the data
#        Analog=f['AnalogData'][tind,:]
#        Ibase=f['BaseIntensity'][tind,goodwl,elind]
        Ipeak = f['PeakIntensity'][tind, goodwl, elind]  # time x wavelength x elevation angle
# %% root out bad channels 2011-03-01 for example
        for i in range(wavelen[goodwl].size):
            if (Ipeak[:, i, :] == 0).all():
                goodwl[i] = False
        """
        astype(float) is critical to avoid overflow of int16 dtype!
        """
        Ipeak = f['PeakIntensity'][tind, goodwl, elind].astype(float)
# %% filter factor per wavelength Rayleigh/PMT * 128
        filtfact = f['FilterFactor'][goodwl]

    Rayleigh = Ipeak * filtfact[None, :, None].astype(float) / 128.

    R = DataArray(data=Rayleigh,
                  dims=['time', 'wavelength', 'elevation'],
                  coords={'time': t[tind], 'wavelength': wavelen[goodwl], 'elevation': elv[elind]})

    return R


def lineratio(R: DataArray, wl: tuple) -> Optional[float]:
    """
    R: brightness in Rayleighs vs. time, wavelength, elevation
    wl: wavelengths to ratio
    """
    try:
        return R.sel(wavelength=wl[0]) / R.sel(wavelength=wl[1])
    except KeyError as e:
        logging.error(f'wavelength {e} not available. skipping ratio')
        return None
