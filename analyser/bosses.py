from enum import IntEnum
from .bossmetrics import *
from evtcparser.parser import StateChange

class DesiredValue(IntEnum):
    LOW = -1
    NONE = 0
    HIGH = 1

class MetricType(IntEnum):
    TIME = 0
    COUNT = 1

class Kind(IntEnum):
    RAID = 1
    EASY = 2
    DUMMY = 3
    FRACTAL = 4

MINUTES = 60

def no_cm(events, boss_instids, agents = None):
    return False

def yes_cm(events, boss_instids, agents = None):
    return True

def cairn_cm_detector(events, boss_instids, agents = None):
    return len(events[events.skillid == 38098]) > 0

def samarog_cm_detector(events, boss_instids, agents = None):
    return len(events[(events.skillid == 37966)&(events.time - events.time.min() < 10000)]) > 0

def mo_cm_detector(events, boss_instids, agents = None):
    return len(events[(events.state_change == 12) & (events.dst_agent == 30000000) & (events.src_instid.isin(boss_instids))]) > 0

def deimos_cm_detector(events, boss_instids, agents = None):
    return len(events[(events.state_change == 12) & (events.dst_agent == 42000000) & (events.src_instid.isin(boss_instids))]) > 0

def dhuum_cm_detector(events, boss_instids, agents = None):
    return len(events[(events.state_change == 12) & (events.dst_agent == 40000000) & (events.src_instid.isin(boss_instids))]) > 0

def ca_cm_detector(events, boss_instids, agents = None):
    return len(events[events.skillid == 53075]) > 0

def largos_cm_detector(events, boss_instids, agents = None):
    return len(events[(events.state_change == 12) & (events.dst_agent == 19219604) & (events.src_instid.isin(boss_instids))]) > 0

def qadim_cm_detector(events, boss_instids, agents = None):
    return len(events[(events.state_change == 12) & (events.dst_agent == 21195636) & (events.src_instid.isin(boss_instids))]) > 0

def skorvald_cm_detector(events, boss_instids, agents = None):
    return len(events[(events.state_change == 12) & (events.dst_agent == 5551340) & (events.src_instid.isin(boss_instids))]) > 0

def soulless_cm_detector(events, boss_instids, agents = None):
    necrosis_events = events[(events.skillid == 47414)&(events.time - events.time.min() < 16000)&(events.is_buffremove == 0)].copy()
    deltas = abs(necrosis_events.time - necrosis_events.time.shift(1))
    deltas.fillna(10000000, inplace=True)
    necrosis_events = necrosis_events.assign(deltas = deltas)
    necrosis_events = necrosis_events[necrosis_events.deltas > 1000]
    print(necrosis_events)
    return len(necrosis_events) > 1

class Metric:
    def __init__(self, name, short_name, data_type, split_by_player = True, split_by_phase = False, desired = DesiredValue.LOW):
        self.name = name
        self.short_name = short_name
        self.long_name = name # TODO
        self.data_type = data_type
        self.desired = desired
        self.split_by_player = split_by_player
        self.split_by_phase = split_by_phase

    def __repr__(self):
        return "%s (%s, %s)" % (self.name, self.data_type, self.desired)

class Boss:
    def __init__(self, name, kind, boss_ids, metrics=None, gather_stats=None, sub_boss_ids=None, key_npc_ids = None, phases=None, despawns_instead_of_dying = False, has_structure_boss = False, success_health_limit = None, success_min_health_limit = None, cm_detector = no_cm, force_single_party = False, non_cm_allowed = True, enrage = None):
        self.name = name
        self.kind = kind
        self.boss_ids = boss_ids
        self.metrics = [] if metrics is None else metrics
        self.sub_boss_ids = [] if sub_boss_ids is None else sub_boss_ids
        self.phases = [] if phases is None else phases
        self.key_npc_ids = [] if key_npc_ids is None else key_npc_ids
        self.despawns_instead_of_dying = despawns_instead_of_dying
        self.has_structure_boss = has_structure_boss
        self.success_health_limit = success_health_limit
        self.success_min_health_limit = success_min_health_limit
        self.cm_detector = cm_detector
        self.force_single_party = force_single_party
        self.non_cm_allowed = non_cm_allowed
        self.gather_boss_specific_stats = gather_stats
        self.enrage = enrage

class Phase:
    def __init__(self, name, important,
                 phase_end_damage_stop=None,
                 phase_end_damage_start=None,
                 phase_end_health=None,
                 phase_skip_health=None,
                 phase_end_boss_id=None,
                 end_on_death=False):
        self.name = name
        self.important = important
        self.phase_end_damage_stop = phase_end_damage_stop
        self.phase_end_damage_start = phase_end_damage_start
        self.phase_end_health = phase_end_health
        self.phase_skip_health = phase_skip_health
        self.phase_end_boss_id = phase_end_boss_id
        self.end_on_death = end_on_death

    def find_end_time(self,
                      current_time,
                      from_boss_events,
                      to_boss_events,
                      health_updates,
                      skill_activations,
                      bosses):
        end_time = None
        relevant_health_updates = health_updates[(health_updates.time >= current_time)]
        damage_gaps = to_boss_events.copy()
        
        if self.phase_end_boss_id is not None:
            bosses_ids = bosses[bosses.prof.isin(self.phase_end_boss_id)].index.values
            relevant_health_updates = relevant_health_updates[relevant_health_updates.src_instid.isin(bosses_ids)]
            damage_gaps = damage_gaps[damage_gaps.dst_instid.isin(bosses_ids)]
            from_boss_events = from_boss_events[from_boss_events.src_instid.isin(bosses_ids)]
            to_boss_events = to_boss_events[to_boss_events.dst_instid.isin(bosses_ids)]
            
        damage_gaps = damage_gaps[(damage_gaps.type == 1) & (damage_gaps.value > 0)]
        previous_gap_time = damage_gaps.time.shift(1)
        gap_deltas = damage_gaps.time - previous_gap_time
        damage_gaps = damage_gaps.assign(delta = gap_deltas, previous = previous_gap_time)    
                        
        if self.phase_skip_health is not None:
            if (not relevant_health_updates.empty) and (relevant_health_updates['dst_agent'].max() < self.phase_skip_health * 100):
                print("{0}: Detected skipped phase - past skip health threshold".format(self.name))
                return current_time    
            
        if self.end_on_death and self.phase_end_boss_id is not None:
            death_events = from_boss_events[(from_boss_events.state_change == StateChange.CHANGE_DEAD)]
            if len(death_events) == len(self.phase_end_boss_id):
                print("{0}: Detected all current boss death".format(self.name))
                return int(death_events['time'].iloc[-1])
                
        if self.phase_end_damage_stop is not None:
            relevant_gaps = damage_gaps[(damage_gaps.time - damage_gaps.delta >= current_time - 100) &
                                        (damage_gaps.delta > self.phase_end_damage_stop)]
                            
            gap_time = None
            if relevant_gaps.empty and (len(damage_gaps.time) > 0 and int(damage_gaps.time.iloc[-1]) >= current_time):
                gap_time = int(damage_gaps.time.iloc[-1])   
            elif not relevant_gaps.empty:
                gap_time = int(relevant_gaps['time'].iloc[0] - relevant_gaps['delta'].iloc[0])
            
            if gap_time is not None:
                relevant_health_updates = relevant_health_updates[relevant_health_updates.time < gap_time]
                if (self.phase_skip_health is not None) and (relevant_health_updates['dst_agent'].min() < (self.phase_skip_health + 2) * 100):
                    print("{0}: Detected skipped next phase".format(self.name))
                else:
                    end_time = gap_time
                    print("{0}: Detected gap of at least {1} at time {2}".format(self.name, self.phase_end_damage_stop, gap_time))

        elif self.phase_end_damage_start is not None:
            relevant_gaps = damage_gaps[(damage_gaps.time >= current_time) &
                                        (damage_gaps.delta > self.phase_end_damage_start)]
            if not relevant_gaps.empty:
                end_time = int(relevant_gaps['time'].iloc[0])
                relevant_health_updates = relevant_health_updates[relevant_health_updates.time < end_time]
                if (self.phase_skip_health is not None) and (relevant_health_updates['dst_agent'].min() < (self.phase_skip_health + 2) * 100):
                    print("{0}: Damage passed skip point, skipping".format(self.name))
                    return current_time
                print("{0}: Detected gap of at least {1} ending at time {2}".format(self.name, self.phase_end_damage_start, end_time))        
                
        if self.phase_end_health is not None:
            if (not relevant_health_updates.empty) and (relevant_health_updates['dst_agent'].max() < self.phase_end_health * 100):
                print("{0}: Detected skipped phase - past phase end health".format(self.name))
                return current_time
            
            #Find health updates below threshold first
            below_health_updates = relevant_health_updates[(relevant_health_updates.dst_agent < self.phase_end_health * 100)]
            if not below_health_updates.empty:
                end_time = current_time = int(below_health_updates['time'].iloc[0])
                print("{0}: Detected health threshold reached at {1}".format(self.name, current_time))
            else:
                relevant_health_updates = relevant_health_updates[(relevant_health_updates.dst_agent >= self.phase_end_health * 100)]
                if relevant_health_updates.empty or health_updates['dst_agent'].min() > (self.phase_end_health + 2) * 100:
                    print("No relevant events above {0} and above {1} health".format(current_time, self.phase_end_health * 100))
                    return None
                end_time = current_time = int(relevant_health_updates['time'].iloc[-1])
            print("{0}: Detected health below {1} at time {2} - prior health: {3}".format(self.name, self.phase_end_health, current_time, relevant_health_updates['dst_agent'].max()))
            
        
        return end_time

BOSS_ARRAY = [
    Boss('Vale Guardian', Kind.RAID, [0x3C4E], enrage = 8 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000, phase_skip_health = 33),
        Phase("First split", False, phase_end_damage_start = 10000, phase_skip_health = 33),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000, phase_skip_health = 1),
        Phase("Second split", False, phase_end_damage_start = 10000, phase_skip_health = 1),
        Phase("Phase 3", True)
    ], metrics = [
        Metric('Blue Guardian Invulnerability Time', 'Blue Invuln', MetricType.TIME, False),
        Metric('Bullets Eaten', 'Bulleted', MetricType.COUNT),
        Metric('Teleports', 'Teleported', MetricType.COUNT)
    ], gather_stats = gather_vg_stats),
    Boss('Gorseval', Kind.RAID, [0x3C45], enrage = 7 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000, phase_skip_health = 33),
        Phase("First souls", False, phase_end_damage_start = 10000, phase_skip_health = 33),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000, phase_skip_health = 1),
        Phase("Second souls", False, phase_end_damage_start = 10000, phase_skip_health = 1),
        Phase("Phase 3", True)
    ], metrics = [
        Metric('Unmitigated Spectral Impacts', 'Slammed', MetricType.COUNT, True, True),
        Metric('Ghastly Imprisonments', 'Imprisoned', MetricType.COUNT),
        Metric('Spectral Darkness', 'Tainted', MetricType.TIME)
    ], gather_stats = gather_gorse_stats),
    Boss('Sabetha', Kind.RAID, [0x3C0F], enrage = 9 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 75, phase_end_damage_stop = 10000, phase_skip_health = 50),
        Phase("Kernan", False, phase_end_damage_start = 10000, phase_skip_health = 50),
        Phase("Phase 2", True, phase_end_health = 50, phase_end_damage_stop = 10000, phase_skip_health = 25),
        Phase("Knuckles", False, phase_end_damage_start = 10000, phase_skip_health = 25),
        Phase("Phase 3", True, phase_end_health = 25, phase_end_damage_stop = 10000, phase_skip_health = 1),
        Phase("Karde", False, phase_end_damage_start = 10000, phase_skip_health = 1),
        Phase("Phase 4", True)
    ], metrics = [
        Metric('Heavy Bombs Undefused', 'Heavy Bombs', MetricType.COUNT, False)
    ], gather_stats = gather_sab_stats),
    Boss('Slothasor', Kind.RAID, [0x3EFB], enrage = 7 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 80, phase_end_damage_stop = 1000, phase_skip_health = 60),
        Phase("Break 1", False, phase_end_damage_start = 1000, phase_skip_health = 60),
        Phase("Phase 2", True, phase_end_health = 60, phase_end_damage_stop = 1000, phase_skip_health = 40),
        Phase("Break 2", False, phase_end_damage_start = 1000, phase_skip_health = 40),
        Phase("Phase 3", True, phase_end_health = 40, phase_end_damage_stop = 1000, phase_skip_health = 20),
        Phase("Break 3", False, phase_end_damage_start = 1000, phase_skip_health = 20),
        Phase("Phase 4", True, phase_end_health = 20, phase_end_damage_stop = 1000, phase_skip_health = 10),
        Phase("Break 4", False, phase_end_damage_start = 1000, phase_skip_health = 10),
        Phase("Phase 5", True, phase_end_health = 10, phase_end_damage_stop = 1000, phase_skip_health = 1),
        Phase("Break 5", False, phase_end_damage_start = 1000, phase_skip_health = 1),
        Phase("Phase 6", True)
    ], metrics = [
        Metric('Tantrum Knockdowns', 'Tantrumed', MetricType.COUNT),
        Metric('Spores Received', 'Spored', MetricType.COUNT),
        Metric('Spores Blocked', 'Spore Blocks', MetricType.COUNT, True, False, DesiredValue.HIGH),
        Metric('Volatile Poison Carrier', 'Poisoned', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Toxic Cloud Breathed', 'Green Goo', MetricType.COUNT, True, False)
    ], gather_stats = gather_sloth_stats),
    Boss('Bandit Trio', Kind.EASY, [0x3ED8, 0x3F09, 0x3EFD], enrage = 9 * MINUTES, success_min_health_limit = 95, phases = [
        #Needs to be a little bit more robust, but it's trio - not the most important fight.
        Phase("Clear 1", True, phase_end_damage_start= 10000),
        Phase("Berg", True, phase_end_damage_stop = 10000),
        Phase("Clear 2", True, phase_end_damage_start= 10000),
        Phase("Zane", True, phase_end_damage_stop = 10000),
        Phase("Clear 3", True, phase_end_damage_start = 10000),
        Phase("Narella", True, phase_end_damage_stop = 10000)
    ], gather_stats = gather_trio_stats),
    Boss('Matthias', Kind.RAID, [0x3EF3], enrage = 10 * MINUTES, success_min_health_limit = 95, phases = [
        #Will currently detect phases slightly early - but probably not a big deal?
        Phase("Ice", True, phase_end_health = 80),
        Phase("Fire", True, phase_end_health = 60),
        Phase("Rain", True, phase_end_health = 40),
        Phase("Abomination", True)
    ], metrics = [
        Metric('Moved While Unbalanced', 'Slipped', MetricType.COUNT),
        Metric('Surrender', 'Surrendered', MetricType.COUNT),
        Metric('Burning Stacks Received', 'Burned', MetricType.COUNT, True, True),
        Metric('Corrupted', 'Corrupted', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Matthias Shards Returned', 'Reflected', MetricType.COUNT, False),
        Metric('Shards Absorbed', 'Absorbed', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Sacrificed', 'Sacrificed', MetricType.COUNT, True, False, DesiredValue.NONE),
        Metric('Well of the Profane Carrier', 'Welled', MetricType.COUNT, True, False, DesiredValue.NONE)
    ], gather_stats = gather_matt_stats),
    Boss('Keep Construct', Kind.RAID, [0x3F6B], enrage = 10 * MINUTES, success_min_health_limit = 95, phases = [
        # Needs more robust sub-phase mechanisms, but this should be on par with raid-heroes.
        Phase("Pre-burn 1", True, phase_end_damage_stop = 15000),
        Phase("Split 1", False, phase_end_damage_start = 15000),
        Phase("Burn 1", True, phase_end_health = 66, phase_end_damage_stop = 15000, phase_skip_health = 33),
        Phase("Pacman 1", False, phase_end_damage_start = 15000, phase_skip_health = 33),
        Phase("Pre-burn 2", True, phase_end_damage_stop = 15000, phase_skip_health = 33),
        Phase("Split 2", False, phase_end_damage_start = 15000, phase_skip_health = 33),
        Phase("Burn 2", True, phase_end_health = 33, phase_end_damage_stop = 15000, phase_skip_health = 1),
        Phase("Pacman 2", False, phase_end_damage_start = 15000, phase_skip_health = 1),
        Phase("Pre-burn 3", True, phase_end_damage_stop = 18000, phase_skip_health = 1),
        Phase("Split 3", False, phase_end_damage_start = 18000, phase_skip_health = 1),
        Phase("Burn 3", True)
    ], metrics = [
        Metric('Correct Orb', 'Correct Orbs', MetricType.COUNT),
        Metric('Wrong Orb', 'Wrong Orbs', MetricType.COUNT),
        Metric('Rifts Hit', 'Rifts Hit', MetricType.COUNT, False, False, DesiredValue.HIGH),
        Metric('Gaining Power', 'Power Gained', MetricType.COUNT, False, False),
        Metric('Magic Blast Intensity', 'Orbs Missed', MetricType.COUNT, False, False)
    ], gather_stats = gather_kc_stats),
    Boss('Xera', Kind.RAID, [0x3F76, 0x3F9E], enrage = 11 * MINUTES, despawns_instead_of_dying = True, success_health_limit = 3, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 51, phase_end_damage_stop = 30000),
        Phase("Leyline", False, phase_end_damage_start = 30000),
        Phase("Phase 2", True),
    ], metrics = [
        Metric('Derangement', 'Deranged', MetricType.COUNT)
    ], gather_stats = gather_xera_stats),
    Boss('Cairn', Kind.RAID, [0x432A], enrage = 8 * MINUTES, success_min_health_limit = 95, metrics = [
        Metric('Displacement', 'Teleported', MetricType.COUNT),
        Metric('Meteor Swarm', 'Shard Hits', MetricType.COUNT),
        Metric('Spatial Manipulation', 'Circles', MetricType.COUNT),
        Metric('Shared Agony', 'Agony', MetricType.COUNT)
    ], cm_detector = cairn_cm_detector, gather_stats = gather_cairn_stats),
    Boss('Mursaat Overseer', Kind.RAID, [0x4314], enrage = 6 * MINUTES, success_min_health_limit = 95, metrics = [
        Metric('Protect', 'Protector', MetricType.COUNT),
        Metric('Claim', 'Claimer', MetricType.COUNT),
        Metric('Dispel', 'Dispeller', MetricType.COUNT),
        Metric('Soldiers', 'Soldiers', MetricType.COUNT, False),
        Metric('Soldier\'s Aura', 'Soldier AOE', MetricType.COUNT),
        Metric('Enemy Tile', 'Enemy Tile', MetricType.COUNT)
    ], cm_detector = mo_cm_detector, gather_stats = gather_mursaat_overseer_stats),
    Boss('Samarog', Kind.RAID, [0x4324], enrage = 11 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000, phase_skip_health = 33),
        Phase("First split", False, phase_end_damage_start = 10000, phase_skip_health = 33),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000, phase_skip_health = 1),
        Phase("Second split", False, phase_end_damage_start = 10000, phase_skip_health = 1),
        Phase("Phase 3", True, phase_end_health=1)
    ], metrics = [
        Metric('Claw', 'Claw', MetricType.COUNT, True, True),
        Metric('Shockwave', 'Shockwave', MetricType.COUNT, True, True),
        Metric('Prisoner Sweep', 'Sweep', MetricType.COUNT, True, True),
        Metric('Charge', 'Charge', MetricType.COUNT, True, False),
        Metric('Anguished Bolt', 'Guldhem Stun', MetricType.COUNT, True, False),
        Metric('Inevitable Betrayal', 'Chose Poorly', MetricType.COUNT, True, False),
        Metric('Bludgeon', 'Bludgeon', MetricType.COUNT, True, False),
        Metric('Fixate', 'Fixate', MetricType.COUNT, True, True),
        Metric('Small Friend', 'Small Friend', MetricType.COUNT, True, True),
        Metric('Big Friend', 'Big Friend', MetricType.COUNT, True, True),
        Metric('Spear Impact', 'Spear Impacts', MetricType.COUNT, True, True)
    ], cm_detector = samarog_cm_detector, gather_stats = gather_samarog_stats),
    Boss('Deimos', Kind.RAID, [0x4302], enrage = 12 * MINUTES, key_npc_ids=[17126], despawns_instead_of_dying = True, has_structure_boss = True, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 10, phase_end_damage_stop = 20000),
        Phase("Phase 2", True)
    ], metrics = [
        Metric('Annihilate', 'Slammed', MetricType.COUNT, True, False),
        Metric('Soul Feast', 'Hand Touches', MetricType.COUNT, True, False),
        Metric('Mind Crush', 'Mind Crush', MetricType.COUNT, True, False),
        Metric('Rapid Decay', 'Black', MetricType.COUNT, True, False),
        Metric('Demonic Shockwave', 'Shockwave', MetricType.COUNT, True, False),
        Metric('Teleports', 'Teleports', MetricType.COUNT, True, False),
        Metric('Tear Consumed', 'Tears Consumed', MetricType.COUNT, True, False)
    ], cm_detector = deimos_cm_detector, gather_stats = gather_deimos_stats),
    Boss('Cairn (CM)', Kind.RAID, [0xFF432A], enrage = 8 * MINUTES, success_min_health_limit = 95, metrics = [
        Metric('Displacement', 'Teleported', MetricType.COUNT),
        Metric('Meteor Swarm', 'Shard Hits', MetricType.COUNT),
        Metric('Spatial Manipulation', 'Circles', MetricType.COUNT),
        Metric('Shared Agony', 'Agony', MetricType.COUNT)
    ], cm_detector = cairn_cm_detector),
    Boss('Mursaat Overseer (CM)', Kind.RAID, [0xFF4314], enrage = 6 * MINUTES, success_min_health_limit = 95, metrics = [
        Metric('Protect', 'Protector', MetricType.COUNT),
        Metric('Claim', 'Claimer', MetricType.COUNT),
        Metric('Dispel', 'Dispeller', MetricType.COUNT),
        Metric('Soldiers', 'Soldiers', MetricType.COUNT, False),
        Metric('Soldier\'s Aura', 'Soldier AOE', MetricType.COUNT),
        Metric('Enemy Tile', 'Enemy Tile', MetricType.COUNT)
    ], cm_detector = mo_cm_detector),
    Boss('Samarog (CM)', Kind.RAID, [0xFF4324], enrage = 11 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 10000, phase_skip_health = 33),
        Phase("First split", False, phase_end_damage_start = 10000, phase_skip_health = 33),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 10000, phase_skip_health = 1),
        Phase("Second split", False, phase_end_damage_start = 10000, phase_skip_health = 1),
        Phase("Phase 3", True, phase_end_health=1)
    ], metrics = [
        Metric('Claw', 'Claw', MetricType.COUNT, True, True),
        Metric('Shockwave', 'Shockwave', MetricType.COUNT, True, True),
        Metric('Prisoner Sweep', 'Sweep', MetricType.COUNT, True, True),
        Metric('Charge', 'Charge', MetricType.COUNT, True, False),
        Metric('Anguished Bolt', 'Guldhem Stun', MetricType.COUNT, True, False),
        Metric('Inevitable Betrayal', 'Chose Poorly', MetricType.COUNT, True, False),
        Metric('Bludgeon', 'Bludgeon', MetricType.COUNT, True, False),
        Metric('Fixate', 'Fixate', MetricType.COUNT, True, True),
        Metric('Small Friend', 'Small Friend', MetricType.COUNT, True, True),
        Metric('Big Friend', 'Big Friend', MetricType.COUNT, True, True),
        Metric('Spear Impact', 'Spear Impacts', MetricType.COUNT, True, True)
    ], cm_detector = samarog_cm_detector),
    Boss('Deimos (CM)', Kind.RAID, [0xFF4302], enrage = 12 * MINUTES, key_npc_ids=[17126], despawns_instead_of_dying = True, has_structure_boss = True, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 10, phase_end_damage_stop = 20000),
        Phase("Phase 2", True)
    ], metrics = [
        Metric('Annihilate', 'Slammed', MetricType.COUNT, True, False),
        Metric('Soul Feast', 'Hand Touches', MetricType.COUNT, True, False),
        Metric('Mind Crush', 'Mind Crush', MetricType.COUNT, True, False),
        Metric('Rapid Decay', 'Black', MetricType.COUNT, True, False),
        Metric('Demonic Shockwave', 'Shockwave', MetricType.COUNT, True, False),
        Metric('Teleports', 'Teleports', MetricType.COUNT, True, False),
        Metric('Tear Consumed', 'Tears Consumed', MetricType.COUNT, True, False)
    ], cm_detector = deimos_cm_detector),
    Boss('Soulless Horror', Kind.RAID, [19767], enrage = 8 * MINUTES, success_min_health_limit = 95, metrics = [
        Metric('Inner Vortex', 'Inner Vortex', MetricType.COUNT, True, False),
        Metric('Outer Vortex', 'Outer Vortex', MetricType.COUNT, True, False),
        Metric('Soul Rift', 'Soul Rift', MetricType.COUNT, True, False),
        Metric('Quad Slash', 'Quad Slash', MetricType.COUNT, True, False),
        Metric('Scythe Hits', 'Scythe Hits', MetricType.COUNT, True, False),
        Metric('Necrosis Received', 'Necrosis', MetricType.COUNT, True, False)
    ], cm_detector = soulless_cm_detector, gather_stats = gather_sh_stats),
    Boss('Dhuum', Kind.RAID, [19450], enrage = 10 * MINUTES, cm_detector = dhuum_cm_detector, success_min_health_limit = 95, phases = [
        Phase("Pre-event", True, phase_end_damage_start = 1),
        Phase("Main", True, phase_end_health = 10, phase_end_damage_stop = 10000),
        Phase("???", False, phase_end_damage_start = 10000),
        Phase("Ritual", True)
    ], metrics = [
        Metric('Messenger', 'Messenger', MetricType.COUNT, True, False),
        Metric('Shackle Hits', 'Shackle Hits', MetricType.COUNT, True, False),
        Metric('Fissured', 'Fissured', MetricType.COUNT, True, False),
        Metric('Putrid Bomb', 'Putrid Bomb', MetricType.COUNT, True, False),
        Metric('Sucked', 'Sucked', MetricType.COUNT, True, False),
        Metric('Death Marked', 'Death Marked', MetricType.COUNT, True, False),
        Metric('Dhuum Gaze', 'Dhuum Gaze', MetricType.COUNT, True, False)
    ], gather_stats = gather_dhuum_stats),
    Boss('Soulless Horror (CM)', Kind.RAID, [0xFF4D37], enrage = 8 * MINUTES, success_min_health_limit = 95, metrics = [
        Metric('Inner Vortex', 'Inner Vortex', MetricType.COUNT, True, False),
        Metric('Outer Vortex', 'Outer Vortex', MetricType.COUNT, True, False),
        Metric('Soul Rift', 'Soul Rift', MetricType.COUNT, True, False),
        Metric('Quad Slash', 'Quad Slash', MetricType.COUNT, True, False),
        Metric('Scythe Hits', 'Scythe Hits', MetricType.COUNT, True, False),
        Metric('Necrosis Received', 'Necrosis Received', MetricType.COUNT, True, False)
    ], cm_detector = soulless_cm_detector),
    Boss('Dhuum (CM)', Kind.RAID, [0xFF4BFA], enrage = 10 * MINUTES, cm_detector = dhuum_cm_detector, success_min_health_limit = 95, phases = [
        Phase("Pre-event", True, phase_end_damage_start = 1),
        Phase("Main", True, phase_end_health = 10, phase_end_damage_stop = 10000),
        Phase("???", False, phase_end_damage_start = 10000),
        Phase("Ritual", True)
    ], metrics = [
        Metric('Messenger', 'Messenger', MetricType.COUNT, True, False),
        Metric('Shackle Hits', 'Shackle Hits', MetricType.COUNT, True, False),
        Metric('Fissured', 'Fissured', MetricType.COUNT, True, False),
        Metric('Putrid Bomb', 'Putrid Bomb', MetricType.COUNT, True, False),
        Metric('Sucked', 'Sucked', MetricType.COUNT, True, False),
        Metric('Death Marked', 'Death Marked', MetricType.COUNT, True, False),
        Metric('Snatched', 'Snatched', MetricType.COUNT, True, False),
        Metric('Dhuum Gaze', 'Dhuum Gaze', MetricType.COUNT, True, False)
    ]),
    Boss('Conjured Amalgamate', Kind.RAID, [0xABC6, 0xFFFFABC6, 0xFFFF9258, 0xFFFF279E], enrage = 8 * MINUTES, cm_detector = ca_cm_detector, success_min_health_limit = 95, phases = [
        # Needs more robust sub-phase mechanisms
        Phase("First Arm", True, phase_end_health = 1.01, phase_end_boss_id = [0xFFFF279E, 0xFFFF9258]),
        Phase("Orb Sweep Burn 1", True, phase_end_damage_stop = 5000, phase_end_health = 50, phase_end_boss_id = [0xFFFFABC6]),
        Phase("Second Arm", True, phase_end_health = 1.01, phase_end_boss_id = [0xFFFF279E, 0xFFFF9258]),
        Phase("Orbs Sweep Burn 2", True, phase_end_damage_stop = 5000, phase_end_health = 25, phase_end_boss_id = [0xFFFFABC6]),
        Phase("Double Arms", True, phase_end_health = 1.01, phase_end_boss_id = [0xFFFF9258, 0xFFFF279E]),
        Phase("Final Burn", True, phase_end_boss_id = [0xFFFFABC6]),
    ], metrics = [
        Metric('Pulverize', 'Slammed', MetricType.COUNT, True, False),
        Metric('Junk Fall', 'Falling Junk', MetricType.COUNT, True, False),
        Metric('Junk Absorption', 'Purple Orbs', MetricType.COUNT, True, False),
    ], gather_stats=gather_ca_stats),
    Boss('Conjured Amalgamate (CM)', Kind.RAID, [0xFFABC6, 0xFFFFABC6, 0xFFFF9258, 0xFFFF279E], enrage = 8 * MINUTES, cm_detector = ca_cm_detector, success_min_health_limit = 95, phases = [
        Phase("First Arm", True, phase_end_health = 1.01, phase_end_boss_id = [0xFFFF279E, 0xFFFF9258]),
        Phase("Orb Sweep Burn 1", True, phase_end_damage_stop = 5000, phase_end_health = 50, phase_end_boss_id = [0xFFFFABC6]),
        Phase("Second Arm", True, phase_end_health = 1.01, phase_end_boss_id = [0xFFFF279E, 0xFFFF9258]),
        Phase("Orbs Sweep Burn 2", True, phase_end_damage_stop = 5000, phase_end_health = 25, phase_end_boss_id = [0xFFFFABC6]),
        Phase("Double Arms", True, phase_end_health = 1.01, phase_end_boss_id = [0xFFFF9258, 0xFFFF279E]),
        Phase("Final Burn", True, phase_end_boss_id = [0xFFFFABC6]),
    ], metrics = [
        Metric('Pulverize', 'Slammed', MetricType.COUNT, True, False),
        Metric('Junk Fall', 'Falling Junk', MetricType.COUNT, True, False),
        Metric('Junk Absorption', 'Purple Orbs', MetricType.COUNT, True, False),
    ]),
    Boss('Largos Twins', Kind.RAID, [0x5271, 0x5261], enrage = 8 * MINUTES, cm_detector = largos_cm_detector, success_min_health_limit = 95, phases = [
        Phase("First Platform", True, phase_end_health = 50, phase_end_boss_id = [0x5271]),
        Phase("Second Platform", True, phase_end_health = 50, phase_end_boss_id = [0x5261]),
        Phase("Third Platforms", True, phase_end_health = 25, phase_end_boss_id = [0x5271, 0x5261]),
        Phase("Fourth Platforms", True)
    ], metrics = [
        Metric('Waterlogged', 'Waterlogged', MetricType.COUNT, True, False),
        Metric('Vapor Rush', 'Charged', MetricType.COUNT, True, False),
        Metric('Geyser', 'Launched (Nikare)', MetricType.COUNT, True, False),
        Metric('Water Bomb', 'Bombed', MetricType.COUNT, True, False),
        Metric('Aquatic Detainment', 'Bubbled', MetricType.COUNT, True, False),
        Metric('Aquatic Aura (Nikare)', 'Aquatic Aura (Nikare)', MetricType.COUNT, True, False),
        Metric('Aquatic Vortex', 'Tornado', MetricType.COUNT, True, False),
        Metric('Sea Swell', 'Launched (Kenut)', MetricType.COUNT, True, False),
        Metric('Vapor Jet', 'Boon Steal', MetricType.COUNT, True, False),
        Metric('Aquatic Aura (Kenut)', 'Aquatic Aura (Kenut)', MetricType.COUNT, True, False),
    ], gather_stats=gather_largos_stats),
    Boss('Largos Twins (CM)', Kind.RAID, [0xFF5271, 0xFF5261], enrage = 8 * MINUTES, cm_detector = largos_cm_detector, success_min_health_limit = 95, phases = [
        Phase("First Platform", True, phase_end_health = 50, phase_end_boss_id = [0x5271]),
        Phase("Second Platform", True, phase_end_health = 50, phase_end_boss_id = [0x5261]),
        Phase("Third Platforms", True, phase_end_health = 25, phase_end_boss_id = [0x5271, 0x5261]),
        Phase("Fourth Platforms", True)
    ], metrics = [
        Metric('Waterlogged', 'Waterlogged', MetricType.COUNT, True, False),
        Metric('Vapor Rush', 'Charged', MetricType.COUNT, True, False),
        Metric('Geyser', 'Launched (Nikare)', MetricType.COUNT, True, False),
        Metric('Water Bomb', 'Bombed', MetricType.COUNT, True, False),
        Metric('Aquatic Detainment', 'Bubbled', MetricType.COUNT, True, False),
        Metric('Aquatic Aura (Nikare)', 'Aquatic Aura (Nikare)', MetricType.COUNT, True, False),
        Metric('Aquatic Vortex', 'Tornado', MetricType.COUNT, True, False),
        Metric('Sea Swell', 'Launched (Kenut)', MetricType.COUNT, True, False),
        Metric('Vapor Jet', 'Boon Steal', MetricType.COUNT, True, False),
        Metric('Aquatic Aura (Kenut)', 'Aquatic Aura (Kenut)', MetricType.COUNT, True, False),
    ]),
    Boss('Qadim', Kind.RAID, [0x51C6, 0x5325, 0x5251, 0x52BF,0x5205], enrage = 13 * MINUTES, cm_detector=qadim_cm_detector, success_min_health_limit = 95, phases = [
        Phase("Hydra", True, phase_end_boss_id = [0x5325], end_on_death=True),
        Phase("Burn", True, phase_end_health = 66, phase_end_boss_id = [0x51C6]),
        Phase("Destroyer", True, phase_end_boss_id = [0x5251], end_on_death=True),
        Phase("Burn 2", True, phase_end_health = 33, phase_end_boss_id = [0x51C6]),
        Phase("Wyverns", True, phase_end_boss_id = [0x52BF,0x5205], end_on_death=True),
        Phase("Jumping", False, phase_end_damage_start = 5000, phase_end_boss_id = [0x51C6]),
        Phase("Final Burn", True, phase_end_boss_id = [0x51C6]),
    ], metrics = [
        Metric('Power of the Lamp', 'Lamp', MetricType.COUNT, True, False),
        Metric('Sea of Flame', 'Qadim Hitbox', MetricType.COUNT, True, False),
        Metric('Flame Wave', 'Knockback', MetricType.COUNT, True, False),
        Metric('Fire Wave', 'Shockwave', MetricType.COUNT, True, False),
        Metric('Fiery Dance', 'Fiery Platform Edges', MetricType.COUNT, True, False),
    ], gather_stats=gather_qadim_stats),
    Boss('Qadim (CM)', Kind.RAID, [0xFF51C6, 0x5325, 0x5251, 0x52BF,0x5205], enrage = 13 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Hydra", True, phase_end_boss_id = [0x5325], end_on_death=True),
        Phase("Burn", True, phase_end_health = 66, phase_end_boss_id = [0x51C6]),
        Phase("Destroyer", True, phase_end_boss_id = [0x5251], end_on_death=True),
        Phase("Burn 2", True, phase_end_health = 33, phase_end_boss_id = [0x51C6]),
        Phase("Wyverns", True, phase_end_boss_id = [0x52BF,0x5205], end_on_death=True),
        Phase("Jumping", False, phase_end_damage_start = 5000, phase_end_boss_id = [0x51C6]),
        Phase("Final Burn", True, phase_end_boss_id = [0x51C6]),
    ], metrics = [
        Metric('Power of the Lamp', 'Lamp', MetricType.COUNT, True, False),
        Metric('Sea of Flame', 'Qadim Hitbox', MetricType.COUNT, True, False),
        Metric('Flame Wave', 'Knockback', MetricType.COUNT, True, False),
        Metric('Fire Wave', 'Shockwave', MetricType.COUNT, True, False),
        Metric('Fiery Dance', 'Fiery Platform Edges', MetricType.COUNT, True, False),
    ]),
    # W7 Bosses
    Boss('Cardinal Adina', Kind.RAID, [22006], enrage = 8 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 75, phase_end_damage_stop = 1000),
        Phase("Hands 1", False, phase_end_damage_start = 1000),
        Phase("Phase 2", True, phase_end_health = 50, phase_end_damage_stop = 1000),
        Phase("Hands 2", False, phase_end_damage_start = 1000),
        Phase("Phase 3", True, phase_end_health = 25, phase_end_damage_stop = 1000),
        Phase("Hands 3", False, phase_end_damage_start = 1000),
        Phase("Phase 4", True)
    ]),
    Boss('Cardinal Sabir', Kind.RAID, [21964], enrage = 9 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 80, phase_end_damage_stop = 1000),
        Phase("Jump Puzzle 1", False, phase_end_damage_start = 1000),
        Phase("Phase 2", True, phase_end_health = 60, phase_end_damage_stop = 1000),
        Phase("Jump Puzzle 2", False, phase_end_damage_start = 1000),
        Phase("Phase 3", True)
    ]),
        Boss('Qadim the Peerless', Kind.RAID, [22000], enrage = 12 * MINUTES, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 80, phase_end_damage_stop = 1000),
        Phase("Fire Phase 1", False, phase_end_damage_start = 1000),
        Phase("Phase 2", True, phase_end_health = 60, phase_end_damage_stop = 1000),
        Phase("Fire Phase 2", False, phase_end_damage_start = 1000),
        Phase("Phase 3", True, phase_end_health = 40, phase_end_damage_stop = 1000),
        Phase("Pylon Break 1", False, phase_end_damage_start = 1000),
        Phase("Phase 4", True, phase_end_health = 30, phase_end_damage_stop = 1000),
        Phase("Pylon Break 2", False, phase_end_damage_start = 1000),
        Phase("Phase 5", True, phase_end_health = 20, phase_end_damage_stop = 1000),
        Phase("Pylon Break 3", False, phase_end_damage_start = 1000),
        Phase("Phase 6", True)
    ]),
    Boss('Standard Kitty Golem', Kind.DUMMY, [16199]),
    Boss('Average Kitty Golem', Kind.DUMMY, [16177]),
    Boss('Vital Kitty Golem', Kind.DUMMY, [16198]),
    Boss('Massive Standard Kitty Golem', Kind.DUMMY, [16178]),
    Boss('Massive Average Kitty Golem', Kind.DUMMY, [16202]),
    Boss('Massive Vital Kitty Golem', Kind.DUMMY, [16169]),
    Boss('Resistant Kitty Golem', Kind.DUMMY, [16176]),
    Boss('Tough Kitty Golem', Kind.DUMMY, [16174]),
    Boss('Skorvald the Shattered', Kind.FRACTAL,[0x44E0], success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 15000, phase_skip_health = 33),
        Phase("First split", False, phase_end_damage_start = 15000, phase_skip_health = 33),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 15000, phase_skip_health = 1),
        Phase("Second split", False, phase_end_damage_start = 15000, phase_skip_health = 1),
        Phase("Phase 3", True, phase_end_health=1)
    ], cm_detector = skorvald_cm_detector, force_single_party = True, non_cm_allowed = False),
    Boss('Artsariiv', Kind.FRACTAL, [0x461d], despawns_instead_of_dying = True, success_health_limit = 1, success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 4000, phase_skip_health = 33),
        Phase("First split", False, phase_end_damage_start = 4000, phase_skip_health = 33),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 4000, phase_skip_health = 1),
        Phase("Second split", False, phase_end_damage_start = 4000, phase_skip_health = 1),
        Phase("Phase 3", True, phase_end_health=1)
    ], cm_detector = yes_cm, force_single_party = True, non_cm_allowed = False),
    Boss('Arkk', Kind.FRACTAL,[0x455f], despawns_instead_of_dying = True, success_health_limit = 1, success_min_health_limit = 95, phases =[
        Phase("100-80", True, phase_end_health = 80, phase_end_damage_stop = 6000, phase_skip_health = 70),
        Phase("First orb", False, phase_end_damage_start = 6000, phase_skip_health = 70),
        Phase("80-70", True, phase_end_health = 70, phase_end_damage_stop = 6000, phase_skip_health = 50),
        Phase("Archdiviner", False, phase_end_damage_start = 6000, phase_skip_health = 50),
        Phase("70-50", True, phase_end_health = 50, phase_end_damage_stop = 6000, phase_skip_health = 40),
        Phase("Second orb", False, phase_end_damage_start = 6000, phase_skip_health = 40),
        Phase("50-40", True, phase_end_health = 40, phase_end_damage_stop = 6000, phase_skip_health = 30),
        Phase("Gladiator", False, phase_end_damage_start = 6000, phase_skip_health = 30),
        Phase("40-30", True, phase_end_health = 30, phase_end_damage_stop = 6000, phase_skip_health = 1),
        Phase("Third orb", False, phase_end_damage_start = 6000, phase_skip_health = 1),
        Phase("30-0", True, phase_end_health = 1, phase_end_damage_stop = 6000)
    ], cm_detector = yes_cm, force_single_party = True, non_cm_allowed = False),
    Boss('MAMA', Kind.FRACTAL, [0x427d], success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 75, phase_end_damage_stop = 3000, phase_skip_health = 50),
        Phase("First split", False, phase_end_damage_start = 3000, phase_skip_health = 50),
        Phase("Phase 2", True, phase_end_health = 50, phase_end_damage_stop = 3000, phase_skip_health = 25),
        Phase("Second split", False, phase_end_damage_start = 3000, phase_skip_health = 50),
        Phase("Phase 3", True, phase_end_health = 25, phase_end_damage_stop = 3000, phase_skip_health = 1),
        Phase("Second split", False, phase_end_damage_start = 3000, phase_skip_health = 1),
        Phase("Phase 4", True, phase_end_health=1)
    ], cm_detector = yes_cm, force_single_party = True, non_cm_allowed = False),
    Boss('Siax', Kind.FRACTAL,[0x4284], success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 5000, phase_skip_health = 33),
        Phase("First split", False, phase_end_damage_start = 5000, phase_skip_health = 33),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 5000, phase_skip_health = 1),
        Phase("Second split", False, phase_end_damage_start = 5000, phase_skip_health = 1),
        Phase("Phase 3", True, phase_end_health=1)
    ], cm_detector = yes_cm, force_single_party = True, non_cm_allowed = False),
    Boss('Ensolyss', Kind.FRACTAL,[0x4234], success_min_health_limit = 95, phases = [
        Phase("Phase 1", True, phase_end_health = 66, phase_end_damage_stop = 15000, phase_skip_health = 33),
        Phase("First split", False, phase_end_damage_start = 15000, phase_skip_health = 33),
        Phase("Phase 2", True, phase_end_health = 33, phase_end_damage_stop = 15000, phase_skip_health = 15),
        Phase("Second split", False, phase_end_damage_start = 15000, phase_skip_health = 15),
        Phase("Phase 3", True, phase_end_health=15, phase_skip_health = 1),
        Phase("Phase 4", True, phase_end_health=1)
    ], cm_detector = yes_cm, force_single_party = True, non_cm_allowed = False)
]
BOSSES = {boss.boss_ids[0]: boss for boss in BOSS_ARRAY}
IDS = {boss.name: boss.boss_ids[0] for boss in BOSS_ARRAY}

BOSS_LOCATIONS = [
    {
        "name": "Raids",
        "all": 'All raid bosses',
        "columns": 3,
        "wings": [
            {
                "name": "Spirit Vale",
                "bosses": [
                    IDS['Vale Guardian'],
                    IDS['Gorseval'],
                    IDS['Sabetha'],
                ],
            },
            {
                "name": "Salvation Pass",
                "bosses": [
                    IDS['Slothasor'],
                    IDS['Bandit Trio'],
                    IDS['Matthias'],
                ],
            },
            {
                "name": "Stronghold of the Faithful",
                "bosses": [
                    IDS['Keep Construct'],
                    IDS['Xera'],
                ],
            },
            {
                "name": "Bastion of the Penitent",
                "bosses": [
                    IDS['Cairn'],
                    IDS['Mursaat Overseer'],
                    IDS['Samarog'],
                    IDS['Deimos'],
                ],
            },
            {
                "name": "Hall of Chains",
                "bosses": [
                    IDS['Soulless Horror'],
                    IDS['Dhuum'],
                ],
            },
            {
                "name": "Mythwright Gambit",
                "bosses": [
                    IDS['Conjured Amalgamate'],
                    IDS['Largos Twins'],
                    IDS['Qadim'],
                ],
            },
            {
                "name": "The Key of Ahdashim",
                "bosses": [
                    IDS['Cardinal Adina'],
                    IDS['Cardinal Sabir'],
                    IDS['Qadim the Peerless'],
                ],
            },            
        ],
    },
    {
        "name": "CM Raids",
        # "all": 'All raid bosses',
        "columns": 3,
        "wings": [
            {
                "name": "Bastion of the Penitent",
                "bosses": [
                    IDS['Cairn (CM)'],
                    IDS['Mursaat Overseer (CM)'],
                    IDS['Samarog (CM)'],
                    IDS['Deimos (CM)'],
                ],
            },
            {
                "name": "Hall of Chains",
                "bosses": [
                    IDS['Soulless Horror (CM)'],
                    IDS['Dhuum (CM)'],
                ],
            },
            {
                "name": "Mythwright Gambit",
                "bosses": [
                    IDS['Conjured Amalgamate (CM)'],
                    IDS['Largos Twins (CM)'],
                    IDS['Qadim (CM)'],
                ],
            },
        ],
    },
    {
        "name": "CM Fractals",
        "all": 'All fractal bosses',
        "columns": 4,
        "wings": [
            {
                "name": "Nightmare",
                "bosses": [
                    IDS['MAMA'],
                    IDS['Siax'],
                    IDS['Ensolyss'],
                ],
            },
            {
                "name": "Shattered Observatory",
                "bosses": [
                    IDS['Skorvald the Shattered'],
                    IDS['Artsariiv'],
                    IDS['Arkk'],
                ],
            },
        ],
    },
#     {
#         "name": "Golems",
#         "all": 'All golem bosses',
#         "columns": 4,
#         "wings": [
#             {
#                 "name": "Massive",
#                 "bosses": [
#                     IDS['Massive Standard Kitty Golem'],
#                     IDS['Massive Average Kitty Golem'],
#                     IDS['Massive Vital Kitty Golem'],
#                 ],
#             },
#             {
#                 "name": "Normal",
#                 "bosses": [
#                     IDS['Standard Kitty Golem'],
#                     IDS['Average Kitty Golem'],
#                     IDS['Vital Kitty Golem'],
#                 ],
#             },
#             {
#                 "name": "Special",
#                 "bosses": [
#                     IDS['Resistant Kitty Golem'],
#                     IDS['Tough Kitty Golem'],
#                 ],
#             },
#         ],
#     },
]
