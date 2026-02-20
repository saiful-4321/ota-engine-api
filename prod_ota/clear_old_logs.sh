#!/bin/sh

### --- This script will clear/remove logs older than 7 days from today. Need to place this script outside of the log folder.
### --- And enable file execution permission [ chmod +x clear_old_logs.sh ]. Also need to add cron job (ROOT) to run this script weekly.

# Change directory to ~/bbtm_api
# cd ~/ota_api

# Get today's date and the date 7 days ago in YYYY-mm-dd format
today=$(date +%Y-%m-%d)
# echo "$today"
seven_days_ago=$(date -d "$today - 7 days" +%Y-%m-%d)
# echo "$seven_days_ago"

# Loop through all log files in the logs directory
for logfile in log/*.log; 
do
    # # Extract the date part from the filename (assuming format is YYYY-mm-dd-logfile.log)
    # # file_date=$(basename "$logfile" | cut -d '-' -f 1-3)

    # Extract the date part from the filename (assuming format is YYYY-mm-dd.log)
    file_date=$(basename "$logfile" .log)
    
    # Check if the file date is older than 7 days ago
    # if [[ "$file_date" < "$seven_days_ago" ]]; ## This line is for bash script    
    if [ "$file_date" \< "$seven_days_ago" ];
    
    then
        # echo "$logfile"
        rm -f "$logfile"
    fi
done
