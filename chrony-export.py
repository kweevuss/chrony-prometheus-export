from prometheus_client import start_http_server, Gauge, Info
import subprocess
import time
import re
import sys
import logging
primary_server = Info("ntp_primary_source", "Primary server marked by chronyc")
primary_server_stratum = Gauge('ntp_primary_source_stratum', 'Stratum level of primary selected server')
primary_server_jitter = Gauge('ntp_primary_source_jitter', 'Jitter reported by primary server')
primary_server_offset = Gauge('ntp_primary_source_offset', 'Jitter reported by primary server')

def run_chrony_command(command,logger):
    try:
        output = subprocess.run(["chronyc", command], capture_output=True,check=True,text=True)
    except subprocess.CalledProcessError:
        logger.info("Chrony does not appear to be running, ensure process is started")
        sys.exit(1)
    lines = output.stdout.split("\n")
    return lines

def normalize_offset(offset,unit):
    #normalize in microseconds
    offset = int(offset)
    #millisecond to microsecond
    if "ms" in unit:
        offset *=1000
    #nanosecond to nanosecond
    elif "ns" in unit:
        offset /=1000
    
    #If unit is already in microseconds (us) then just return
    return offset
    

def find_active_sources(output):
    time_data = {}
   
    for line in output:
        #Find the offset in the output: in []
        #- GPS                           0   8   377   226    -68ms[  -68ms] +/-  200ms
        offset_search = (r"\[([^\]]+)\]")
        offset_parsed = re.findall(offset_search,line)
        #Find a match and product 3 groups. +|-, numberical offset value, unit
        if not offset_parsed:
            offset_parsed = ["0us"]
        offset_search = ("\s*([+-])(\d+)(\w+)")
        offset = re.findall(offset_search,offset_parsed[0])
        if offset:
            offset_mathmatical,offset_value,offset_unit = offset[0]
        else: 
            offset_mathmatical = "+"
            offset_value = "0"
            offset_unit = "us"
        
        offset_value = normalize_offset(offset_value,offset_unit)
        
        #Search for the +/- value for jitter and the unit
        jitter_search = (r".+\+/-\s+(\d+)(\w+)")
        jitter_parsed = re.findall(jitter_search,line)
        if not jitter_parsed:
            jitter_value = "0"
            jitter_unit = "us"
        else:
            jitter_value,jitter_unit = jitter_parsed[0]
        if jitter_value:
            jitter_value = normalize_offset(jitter_value,jitter_unit)
        if "*" in line:
            time_data[line.split()[1]] = {"stratum" : line.split()[2], "poll" : line.split()[3], "reach" : line.split()[4], "sample" : line.split()[6], "server_status" : "preferred_server", "offset_mathmatical" : offset_mathmatical, 'offset_value': offset_value, "jitter_value" : jitter_value}
        elif "+" in line:
            time_data[line.split()[1]] = {"stratum" : line.split()[2], "poll" : line.split()[3], "reach" : line.split()[4], "sample" : line.split()[6], "server_status" : "combined_server", "offset_mathmatical" : offset_mathmatical, 'offset_value': offset_value, "jitter_value" : jitter_value}
        elif "-" in line:
            time_data[line.split()[1]] = {"stratum" : line.split()[2], "poll" : line.split()[3], "reach" : line.split()[4], "sample" : line.split()[6], "server_status" : "not_combined_server", "offset_mathmatical" : offset_mathmatical, 'offset_value': offset_value, "jitter_value" : jitter_value}   
    return time_data



def export_data(time_data):
    for entry in time_data:
        if time_data[entry]["server_status"] == "preferred_server":
            primary_server_stratum.set(time_data[entry]['stratum'])
            primary_server.info({"server": entry, "stratum" : time_data[entry]['stratum']})
            primary_server_offset.set(f"{time_data[entry]['offset_mathmatical']}{(time_data[entry]['offset_value'])}")
            primary_server_jitter.set(f"{(time_data[entry]['jitter_value'])}")


def main():
    logger = logging.getLogger("chrony-export")
    logger = logging.getLogger("myservice")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.info("Logging initialized")
    start_http_server(9123)

    while True:
        output = run_chrony_command("sources",logger)
        time_data = find_active_sources(output)
        export_data(time_data)
        time.sleep(10)


if __name__ == "__main__":
    main()
