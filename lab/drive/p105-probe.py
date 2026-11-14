import sys,json
from dataclasses import replace
from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES,SimConfig,Simulator
for target in [6,5,4,3]:
 cfg=SimConfig(**CAR_PROFILES['nominal'],map_tilt=.0065,dead_zone=.25,delay=.14,max_time=160,gps_wrong=0,gps_dropout=0,path_missing=0,damage_probability=0,outlier_probability=0,noise_degrees=.5,path_noise=.15,path_spacing=6,path_horizon=90)
 sim=Simulator(((0,0),(0,150),(150,150)),config=cfg);driver=Driver(replace(drive_config(['style=bold']),turn_speed=target));err=0;entries=[];lowest=99
 while sim.time<160:
  r,m=sim.observe();c=driver.step(r,sim.time,m,speed=sim.observed_speed);e,p=sim._route_position()
  if e>err:err=e;peak=(round(sim.x,2),round(sim.y,2),round(sim.speed,2),driver.speed_reason)
  if not entries and p>145:entries.append(sim.speed)
  if 135<=p<=170:lowest=min(lowest,sim.speed)
  sim.advance(c)
  if p>=sim.length-3:break
 print(target,round(err,3),peak,'entry',entries,'low',lowest,'time',sim.time,flush=True)
