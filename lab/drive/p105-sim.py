"""Serial P105 closed-loop matrix, retaining the five metre and seven m/s bounds."""
import json
from pathlib import Path
from statistics import median
from p98_replay import baseline
from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES,SimConfig,Simulator,drive_through_roads
OUT=Path(__file__).resolve().parent
ROADS={'town-1':((0.,0.),(0.,150.),(150.,150.)), 'town-2':((0.,0.),(0.,150.),(150.,150.),(150.,300.)),**drive_through_roads()}


def run(cls,config,road,profile,tilt):
 town=road.startswith('town');cfg=SimConfig(**CAR_PROFILES[profile],map_tilt=tilt,dead_zone=.25,delay=.14,max_time=300,
  gps_wrong=0,gps_dropout=0,path_missing=0,damage_probability=0,outlier_probability=0,noise_degrees=.5,path_noise=.15,
  path_spacing=6 if town else 3,path_horizon=90 if town else 105)
 sim=Simulator(ROADS[road],config=cfg);driver=cls(config);error=0;entries=[];lowest=99;cruise=[];brakes=0
 corners=[150,300] if road=='town-2' else [150] if town else []
 while sim.time<cfg.max_time:
  r,m=sim.observe();command=driver.step(r,sim.time,m,speed=sim.observed_speed);e,p=sim._route_position();error=max(error,e)
  if len(entries)<len(corners) and p>=corners[len(entries)]-5:entries.append(sim.speed)
  if 135<=p<=170:lowest=min(lowest,sim.speed)
  if 80<p<100:cruise.append(sim.speed)
  if road=='kilometre' and 50<p<975 and command.brake>0:brakes+=1
  sim.advance(command)
  if p>=sim.length-3:break
 return dict(reached=p>=sim.length-3,time=round(sim.time,3),max_error=round(error,4),entries=[round(v,3) for v in entries],
  minimum_turn_speed=round(lowest,3) if town else None,cruise_min=round(min(cruise),3) if cruise else None,
  freeway_brake_ticks=brakes,bounds_pass=p>=sim.length-3 and error<=5 and (not entries or max(entries)<=7))


def main():
 old,cfg=baseline();out=[]
 for label,cls,config,tilt in [('before-affine',old,cfg,0),('before-tilted',old,cfg,.0065),('after-tilted',Driver,drive_config(['style=bold']),.0065)]:
  for name in ROADS:
   for profile in CAR_PROFILES:
    row=dict(variant=label,road=name,profile=profile,**run(cls,config,name,profile,tilt));out.append(row)
   group=[r for r in out if r['variant']==label and r['road']==name]
   print(label,name,'pass',sum(r['bounds_pass'] for r in group),'/',len(group),'max_error',max(r['max_error'] for r in group),'median_time',median(r['time'] for r in group),flush=True)
 (OUT/'p105-simulator.json').write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
