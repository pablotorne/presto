#!/usr/bin/env python
import struct, getopt, sys, umath, fftfit, psr_utils
import Numeric as Num
from infodata import infodata
from bestprof import bestprof
from prepfold import pfd
from polycos import polycos
from psr_constants import *
from types import StringType, FloatType, IntType

scopes = {'GBT':'1', 'Arecibo':'3', 'Parkes':'7', 'GMRT': 'r'}

def measure_phase(profile, template):
    """
    measure_phase(profile, template):
        Call FFTFIT on the profile and template to determine the
            following parameters: shift,eshift,snr,esnr,b,errb,ngood
            (returned as a tuple).  These are defined as in Taylor's
            talk at the Royal Society.
    """
    c,amp,pha = fftfit.cprof(template)
    pha.savespace()
    pha1 = pha[0]
    pha = umath.fmod(pha-Num.arange(1,len(pha)+1)*pha1,TWOPI)
    shift,eshift,snr,esnr,b,errb,ngood = fftfit.fftfit(profile,amp,pha)
    return shift,eshift,snr,esnr,b,errb,ngood

def usage():
    print """
usage:  get_TOAs.py [options which must include -t or -g] pfd_file
  [-h, --help]                       : Display this help
  [-s numsub, --subbands=numsub]     : Divide the fold into numsub subbands
  [-n numTOAs, --numtoas=numTOAs]    : Divide the fold into numTOAs parts
  [-d DM, --dm=DM]                   : Re-combine subbands at DM
  [-f, --FFTFITouts]                 : Print all FFTFIT outputs and errors
  [-g gausswidth, --gaussian=width]  : Use a Gaussian template of FWHM width
  [-t templateprof, --template=prof] : The template .bestprof file to use
  [-k subs_list, --kill=subs_list]   : List of subbands to ignore
  [-e, --event]                      : The .pfd file was made with events
  pfd_file                           : The .pfd file containing the folds

  The program generates TOAs from a .pfd file using Joe Taylor's
  FFTFIT program. The TOAs are output to STDOUT.  Typically, the .pfd
  file is created using prepfold with the "-timing" flag and an
  appropriate .par file on either a topocentric time series or raw
  telescope data.  But barycentric folds or folds of barycentered
  events are also acceptable.  The most important thing about the
  fold, though, is that it must have been made using "-nosearch"! 
  (Note: "-timing" implies "-nosearch")
  
  A typical example would be something like:
      
      get_TOAs.py -n 30 -t myprof.bestprof -k 0,20-23 myprof.pfd | \\
          tail -28 >> good.tim
      
  which would extract 30 TOAs (the default number of slices or parts
  in time for "prepfold -timing" is 60) from a fold made from some raw
  radio telescope data.  The command would ignore (i.e. zero-out)
  subbands 0, 20, 21, 22, and 23 (e.g.  due to interference) and then
  ignore the first 2 TOAs with the tail command.
  
  If you don't specify "-n", the default number of parts in the fold
  is assumed, but if you don't specify "-s", all the subbands (if any
  are present) are integrated together.
  
  If you specify the "-f" flag, an additional line of output is
  displayed for each TOA that shows the "b +/- berr" and "SNR +/-
  SNRerr" params from FFTFIT.
  
"""

if __name__ == '__main__':
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hefs:n:d:g:t:o:k:e:",
                                   ["help", "event", "FFTFITouts", "subbands=", 
				    "numtoas=", "dm=", "gaussian=", "template=",
                                    "offset=", "kill="])
                                    
    except getopt.GetoptError:
        # print help information and exit:
        usage()
        sys.exit(2)
    if len(sys.argv)==1:
        usage()
        sys.exit(2)
    lowfreq = None
    DM = 0.0
    gaussianwidth = 0.1
    templatefilenm = None
    numsubbands = 1
    numtoas = 1
    otherouts = 0
    offset = 0.0
    events = 0
    kill = []
    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        if o in ("-f", "--FFTFITouts"):
	    otherouts = 1
	if o in ("-e", "--event"):
	    lowfreq = 0.0
	    DM = 0.0
	    events = 1
	if o in ("-s", "--subbands"):
            numsubbands = int(a)
        if o in ("-n", "--numtoas"):
            numtoas = int(a)
            if numtoas==0:
                sys.exit()
        if o in ("-d", "--dm"):
            DM = float(a)
        if o in ("-g", "--gaussian"):
            gaussianwidth = float(a)
        if o in ("-t", "--template"):
            templatefilenm = a
        if o in ("-o", "--offset"):
            offset = float(a)
        if o in ("-k", "--kill"):
            for subs in a.split(','):
                if (subs.find("-") > 0):
                    lo, hi = subs.split("-")
                    kill.extend(range(int(lo), int(hi)+1))
                else:
                    kill.append(int(subs))

    # Read key information from the bestprof file
    fold = bestprof(sys.argv[-1]+".bestprof")
    timestep_sec = fold.T / numtoas
    timestep_day = timestep_sec / SECPERDAY
    fold.epoch = fold.epochi+fold.epochf

    # Read the prepfold output file and the binary profiles
    fold_pfd = pfd(sys.argv[-1])
    
    # Over-ride the DM that was used during the fold
    if (DM!=0.0):
        fold_pfd.bestdm = DM
    if (fold_pfd.numchan==1 and DM==0.0 and events):
        fold_pfd.bestdm = 0.0
        fold_pfd.numchan = 1

    # Kill any required channels and/or subband
    fold_pfd.kill_subbands(kill)

    # De-disperse at the requested DM
    fold_pfd.dedisperse()
    
    # Combine the profiles as required
    profs = fold_pfd.combine_profs(numtoas, numsubbands)

    # PRESTO de-disperses at the high frequency channel so determine a
    # correction to the middle of the band
    if not events:
	subpersumsub = fold_pfd.nsub/numsubbands
	# Calculate the center of the summed subband freqs and delays
	sumsubfreqs = (Num.arange(numsubbands)+0.5)*subpersumsub*fold_pfd.subdeltafreq + \
                      (fold_pfd.lofreq-0.5*fold_pfd.chan_wid)
	sumsubdelays = (psr_utils.delay_from_DM(fold_pfd.bestdm, sumsubfreqs) -
                        fold_pfd.hifreqdelay)/SECPERDAY
    else:
	fold_pfd.subfreqs = asarray([0.0])
	sumsubfreqs = asarray([0.0])
	sumsubdelays = asarray([0.0])

    # Read the template profile
    if templatefilenm is not None:
        template_fold = bestprof(templatefilenm)
        template = template_fold.normalize()
    else:
        template = psr_utils.gaussian_profile(fold_pfd.proflen, 0.0, gaussianwidth)
        template = template / max(template)

    # Determine the Telescope used
    if (not fold.topo):
        obs = '@'  # Solarsystem Barycenter
    else:
        try: obs = scopes[fold_pfd.telescope.split()[0]]
	except KeyError:  print "Unknown telescope!!!"

    # Read the polyco file (if required)
    if (fold.psr and fold.topo):
        pcs = polycos(fold.psr, sys.argv[-1]+".polycos")
        (fold.phs0, fold.f0) = pcs.get_phs_and_freq(fold.epochi, fold.epochf)
        fold.f1 = fold.f2 = 0.0
    else:
        pcs = None
        fold.phs0 = 0.0
        (fold.f0, fold.f1, fold.f2) = psr_utils.p_to_f(fold.p0, fold.p1, fold.p2)

    #
    # Calculate the TOAs
    #

    for ii in range(numtoas):

        # The .pfd file was generated using -nosearch and a specified
        # folding period, p-dot, and p-dotdot (or f, f-dot, and f-dotdot).
        if (pcs is None):
            # Time at the middle of the interval in question
            midtime = fold.epoch + (ii+0.5)*timestep_day
            p = 1.0/psr_utils.calc_freq(midtime, fold.epoch, fold.f0, fold.f1, fold.f2)
            t0 = psr_utils.calc_t0(midtime, fold.epoch, fold.f0, fold.f1, fold.f2)
        # The .pfd file was folded using polycos
        else:
            # Time at the middle of the interval in question
            mjdf = fold.epochf + (ii+0.5)*timestep_day
            (phs, f0) = pcs.get_phs_and_freq(fold.epochi, mjdf)
            phs -= fold.phs0
            p = 1.0/fold.f0
            t0 = fold.epochi+mjdf - phs*p/SECPERDAY

        for jj in range(numsubbands):
            prof = profs[ii][jj]

            # Make sure that the template and the data have the same number of bins
            if (not len(template)==fold_pfd.proflen):
                if (not ((len(template)%fold_pfd.proflen)==0 or
                         (fold_pfd.proflen%len(template))==0)):
                    if not ii and not jj:
                        sys.stderr.write("WARNING!: Lengths of template (%d) and data (%d) are incompatible!  Skipping '%s'!\n" % (len(template), fold_pfd.proflen, fold_pfd.filenm))
                    continue
                # Interpolate the data
                if (len(template) > fold_pfd.proflen):
                    prof = psr_utils.linear_interpolate(prof, len(template)/fold_pfd.proflen)
                    if not ii and not jj:
                        sys.stderr.write("Note: Interpolating the data for '%s'\n"%fold_pfd.filenm)
                # Interpolate the template
                elif (1):
                    template = psr_utils.linear_interpolate(template, fold_pfd.proflen/len(template))
                    if not ii and not jj:
                        sys.stderr.write("Note: Interpolating the template for '%s'\n"%fold_pfd.filenm)
                # Downsample the data (Probably not a good idea)
                else:
                    prof = psr_utils.downsample(prof, fold_pfd.proflen/len(template))
                    if not ii and not jj:
                        sys.stderr.write("Note:  Downsampling the data for '%s'\n"%fold_pfd.filenm)

            try:
                # Try using FFTFIT first
                shift,eshift,snr,esnr,b,errb,ngood = measure_phase(prof, template)
                # tau and tau_err are the predicted phase of the pulse arrival
                tau, tau_err = shift/len(prof), eshift/len(prof)
                # Note: "error" flags are shift = 0.0 and eshift = 999.0
                
                # If that failed, use a time-domain correlation
		if (umath.fabs(shift) < 1e-7 and
		    umath.fabs(eshift-999.0) < 1e-7):
		    # Not enough structure in the template profile for FFTFIT
		    # so use time-domain correlations instead
		    tau = psr_utils.measure_phase_corr(prof, template)
		    # This needs to be changed
		    tau_err = 0.1/len(prof)

                # Send the TOA to STDOUT
		psr_utils.write_princeton_toa(t0+(tau*p+offset)/SECPERDAY+sumsubdelays[jj],
                                              tau_err*p*1000000.0,
                                              sumsubfreqs[jj], fold_pfd.bestdm, obs=obs)
		if (otherouts):
		    print "FFTFIT results:  b = %.4g +/- %.4g   SNR = %.4g +/- %.4g" % \
		        (b, errb, snr, esnr)

	    except ValueError, fftfit.error:
                pass