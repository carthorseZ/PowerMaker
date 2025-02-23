#!/usr/bin/env python3

# Importing configeration
from datetime import time
import config

# Importing supporting functions
from powermakerfunctions import *

# Importing modules
import logging # flexible event logging
import math # mathematical functions
from time import sleep  # To add delay
from numpy import interp  # To scale values
import pymysql

# Logging
logging.basicConfig(level=logging.INFO, format=f'%(asctime)s {"PROD" if config.PROD else "TEST"} %(message)s') 

conn = create_db_connection()
c = conn.cursor()
while(True):
    try:
        #get current state
        status = "unknown"
        spot_price = get_spot_price()        
        spot_price_avg, spot_price_min, spot_price_max, import_price, export_price = get_spot_price_stats()
        solar_generation = get_solar_generation()
        power_load = get_existing_load()
        cdp = is_CPD()
        battery_charge, battery_low, battery_full = get_battery_status()
        override, suggested_IE = get_override()     

        # make decision based on current state
        if (override):
            #Manual override
            if (suggested_IE<0):
                status = f"Exporting - Manual Override"
                discharge_to_grid(suggested_IE)
            elif (suggested_IE>0):
                status = f"Importing - Manual Override"
                charge_from_grid(suggested_IE)
            else:
                status = f"No I/E - Manual Override"
                reset_to_default() 
        elif spot_price<= config.LOW_PRICE_IMPORT and not battery_full:
            #spot price less than Low price min import
            status = "Importing - Spot price < min"
            suggested_IE = config.IE_MAX_RATE
            charge_from_grid(suggested_IE)
        elif spot_price>export_price and not battery_low:
            #export power to grid if price is greater than calc export price
            status = f"Exporting - Spot Price High"
            suggested_IE = calc_discharge_rate(spot_price,export_price,spot_price_max)
            discharge_to_grid(suggested_IE)
        elif cdp:
            #there is CPD active so immediately go into low export state
            status = "Exporting - CPD active"
            discharge_to_grid(config.IE_MIN_RATE)
        elif spot_price<= import_price and not battery_full:
            #import power from grid if price is less than calc export price
            status = "Importing - Spot price low"
            suggested_IE = calc_charge_rate(spot_price,import_price,spot_price_min)
            charge_from_grid(suggested_IE)
        else: 
            #Stop any Importing or Exporting activity  
            reset_to_default() 
            if battery_low:
                status = f"No I/E - Battery Low @ {battery_charge} %"
            elif battery_full:
                status = f"No I/E - Battery Ful @ {battery_charge} %"
            else:
                status = f"No I/E - Battery OK @ {battery_charge} %"
        
        actual_IE = get_grid_load()
        c.execute(f"INSERT INTO DataPoint (SpotPrice, AvgSpotPrice, SolarGeneration , PowerLoad , BatteryCharge , Status, ActualIE, SuggestedIE) VALUES ({spot_price}, {spot_price_avg}, {solar_generation}, {power_load}, {battery_charge}, '{status}', {actual_IE}, {suggested_IE})")       
        #log and save record
        logging.info(f"Status {status} \n" )
        conn.commit()

    except Exception as e:
        error = str(e)
        if error == "SpotPriceUnavailable":                
            status = "ERROR Spot Price Unavailable"
            logging.info(f"Status {status}" )
            c.execute(f"INSERT INTO DataPoint (SpotPrice, AvgSpotPrice, SolarGeneration , PowerLoad , BatteryCharge , Status, ActualIE, SuggestedIE) VALUES (0, 0, 0, 0, 0, '{status}', 0, 0)")
            conn.commit()
        elif error == "DatabaseUnavailable":                
            status = "Database Unavailable"
            logging.info(f"Status {status}" )
            c.execute(f"INSERT INTO DataPoint (SpotPrice, AvgSpotPrice, SolarGeneration , PowerLoad , BatteryCharge , Status, ActualIE, SuggestedIE) VALUES (0, 0, 0, 0, 0, '{status}', 0, 0)")
            conn.commit()
       
        #try and stop all I/E as an exception has occurred
        try:
            reset_to_default()
            status = "ERROR occurred I/E has been stopped"
        except Exception as e:
            error = str(e)
            status = f"ERROR unable to stop I/E: {error}"

        logging.info(f"Status {status} \n" )
        c.execute(f"INSERT INTO DataPoint (SpotPrice, AvgSpotPrice, SolarGeneration , PowerLoad , BatteryCharge , Status, ActualIE, SuggestedIE) VALUES (0, 0, 0, 0, 0, '{status}', 0, 0)")
        conn.commit()
    
    sleep(config.DELAY)
