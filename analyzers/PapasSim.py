from heppy.framework.analyzer import Analyzer
from heppy.particles.fcc.particle import Particle 

import math
from heppy.papas.simulator import Simulator
from heppy.papas.vectors import Point
from heppy.papas.pfobjects import Particle as PFSimParticle
from heppy.papas.toyevents import particles
from heppy.display.core import Display
from heppy.display.geometry import GDetector
from heppy.display.pfobjects import GTrajectories
from heppy.papas.pfalgo.distance  import Distance

from heppy.papas.pfalgo.pfinput import PFInput
from heppy.papas.mergedclusterbuilder import MergedClusterBuilder
from heppy.papas.data.comparer import ClusterComparer, TrackComparer
from heppy.papas.data.pfevent import PFEvent
from ROOT import TLorentzVector, TVector3


#todo following Alices merge and reconstruction work
# - add muons and electrons back into the particles, these
#   particles are not yet handled by alices reconstruction
#   they are (for the time being) excluded from the simulation rec particles in order that particle
#   comparisons can be made (eg # no of particles)

class PapasSim(Analyzer):
    '''Runs PAPAS, the PArametrized Particle Simulation.

    Example configuration: 

    from heppy.analyzers.PapasSim import PapasSim
    from heppy.papas.detectors.CMS import CMS
    papas = cfg.Analyzer(
        PapasSim,
        instance_label = 'papas',
        detector = CMS(),
        gen_particles = 'gen_particles_stable',
        sim_particles = 'sim_particles',
        merged_ecals = 'ecal_clusters',
        merged_hcals = 'hcal_clusters',
        tracks = 'tracks',
        #rec_particles = 'sim_rec_particles', # optional - will only do a simulation reconstruction if a name is provided
        rec_particles_no_leptons = 'rec_particles_no_leptons', #only there for verification purposes #TODO make optional
        smeared = 'sim_leptons', 
        history = 'history_nodes', 
        display_filter_func = lambda ptc: ptc.e()>1.,
        display = False,
        verbose = True
    )
    
    detector:      Detector model to be used. 
    gen_particles: Name of the input gen particle collection
    sim_particles: Name extension for the output sim particle collection. 
                   Note that the instance label is prepended to this name. 
                   Therefore, in this particular case, the name of the output 
                   sim particle collection is "papas_sim_particles".
    merged_ecals: Name for the merged clusters created by simulator              
    merged_hcals: Name for the merged clusters created by simulator             
    tracks:       Name for smeared tracks created by simulator              
    
    rec_particles: Optional. Name extension for the reconstructed particles created by simulator
                   This is retained for the time being to allow two reconstructions to be compared
                   Reconstruction will occur iff this parameter is provided
                   Same comments as for the sim_particles parameter above.
    rec_particles_no_leptons: Name extension for the reconstructed particles created by simulator
                   without electrons and muons
                   Will only be produced if the rec_particles is provided
                   This is retained for the time being to allow two reconstructions to be compared
                   Same comments as for the sim_particles parameter above.
    smeared: Name for smeared leptons 
    history: Optional name for the history node, set to None if not needed
    display      : Enable the event display
    verbose      : Enable the detailed printout.
    '''

    def __init__(self, *args, **kwargs):
        super(PapasSim, self).__init__(*args, **kwargs)
        self.detector = self.cfg_ana.detector
        self.simulator = Simulator(self.detector,
                                   self.mainLogger)
        self.simname = '_'.join([self.instance_label,  self.cfg_ana.sim_particles])
        
        self.do_reconstruct = False
        if hasattr(self.cfg_ana, 'rec_particles') :
            self.do_reconstruct = True
            self.recname = '_'.join([self.instance_label,  self.cfg_ana.rec_particles])
        self.rec_noleptonsname = '_'.join([self.instance_label,  self.cfg_ana.rec_particles_no_leptons])
        self.smearedname =  '_'.join([self.instance_label,  self.cfg_ana.smeared])
        self.tracksname =  self.cfg_ana.tracks  
        self.mergedecalsname = self.cfg_ana.merged_ecals
        self.mergedhcalsname = self.cfg_ana.merged_hcals
        
        self.is_display = self.cfg_ana.display
        if self.is_display:
            self.init_display()        

    def init_display(self):
        self.display = Display(['xy','yz'])
        self.gdetector = GDetector(self.detector)
        self.display.register(self.gdetector, layer=0, clearable=False)
        self.is_display = True

    def process(self, event):
        '''
           event must contain
           
           event will gain
             ecal_clusters:- smeared merged clusters from simulation)
             hcal_clusters:- 
             tracks:       - tracks from simulation
             baseline_particles:- simulated particles (excluding electrons and muons)
             sim_particles - simulated particles including electrons and muons
             
             
        '''
        event.simulator = self 
        if self.is_display:
            self.display.clear()
        pfsim_particles = []
        gen_particles = getattr(event, self.cfg_ana.gen_particles)
        self.simulator.simulate( gen_particles , self.do_reconstruct)
        pfsim_particles = self.simulator.ptcs
        if self.is_display:
            self.display.register( GTrajectories(pfsim_particles),
                                   layer=1)
        #these are the particles before simulation        
        simparticles = sorted( pfsim_particles,
                               key = lambda ptc: ptc.e(), reverse=True)
        smearedparticles = sorted( self.simulator.smeared,
                                   key = lambda ptc: ptc.e(), reverse=True)        
        setattr(event, self.simname, simparticles)
        setattr(event, self.smearedname, smearedparticles) # leptons

        
        if self.do_reconstruct:
            #these are the reconstructed (via simulation) particles  including electrons and muons
            particles = sorted( self.simulator.particles,
                            key = lambda ptc: ptc.e(), reverse=True)
        
            #these are the reconstructed (via simulation) particles excluding muons and electrons         
            origparticles = sorted( self.simulator.pfsequence.pfreco.particles,
                                   key = lambda ptc: ptc.e(), reverse=True)
            setattr(event, self.recname, particles)          
            setattr(event, self.rec_noleptonsname, origparticles)
                
            
        
       
        #extract the tracks and clusters (extraction is prior to Colins merging step)
        event.tracks = dict()
        event.ecal_clusters = dict()
        event.hcal_clusters = dict()
        
        if "tracker" in self.simulator.pfinput.elements :
            for element in self.simulator.pfinput.elements["tracker"]:
                event.tracks[element.uniqueid] = element 
        if "ecal_in" in self.simulator.pfinput.elements :        
            for element in self.simulator.pfinput.elements["ecal_in"]:
                event.ecal_clusters[element.uniqueid] = element 
        if "hcal_in" in self.simulator.pfinput.elements :
            for element in self.simulator.pfinput.elements["hcal_in"]:
                event.hcal_clusters[element.uniqueid] = element 
        ruler = Distance()
       
        #Now merge the simulated clusters and tracks as a separate pre-stage (prior to new reconstruction)        
        # and set the event to point to the merged cluster
        pfevent =  PFEvent(event, 'tracks', 'ecal_clusters', 'hcal_clusters')
        merged_ecals = MergedClusterBuilder("ecal_in", pfevent, ruler).merged
        setattr(event, self.mergedecalsname, merged_ecals)
        merged_hcals = MergedClusterBuilder("hcal_in", pfevent, ruler).merged
        setattr(event, self.mergedhcalsname, merged_hcals)        
        
        ####if uncommented this will use the original reconstructions to provide the ready merged tracks and clusters
        #event.ecal_clusters = dict()
        #event.hcal_clusters = dict()        
        #for element in self.simulator.pfsequence.elements :
            #elif element.__class__.__name__ == 'SmearedCluster' and element.layer == 'ecal_in': 
                #event.ecal_clusters[element.uniqueid] = element
            #elif element.__class__.__name__ == 'SmearedCluster' and element.layer == 'hcal_in': 
                #event.hcal_clusters[element.uniqueid] = element
            #else :            
                #print element.__class__.__name__ 
                #assert(False)
       
        ###if uncommented will check that cluster merging is OK   (compare new merging module with Colins merging)    
        #event.origecal_clusters = dict()
        #event.orighcal_clusters = dict()
        #for element in self.simulator.pfsequence.elements :
            #if element.__class__.__name__ == 'SmearedCluster' and element.layer == 'ecal_in': 
                #event.origecal_clusters[element.uniqueid] = element
            #elif element.__class__.__name__ == 'SmearedCluster' and element.layer == 'hcal_in': 
                #event.orighcal_clusters[element.uniqueid] = element
        #ClusterComparer(event.origecal_clusters,event.ecal_clusters)
        #ClusterComparer(event.orighcal_clusters,event.hcal_clusters)
        #event.othertracks =  dict()
        #for element in self.simulator.pfsequence.elements :
            #if element.__class__.__name__ == 'SmearedTrack': 
                #event.othertracks[element.uniqueid] = element        
        #assert (len(event.tracks) == len(event.othertracks))
       
        pass

        
