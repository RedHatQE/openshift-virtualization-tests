# CNV-QE-network
### General configurations
#### VLAN
The current supported vlan tags range in RH labs is 1000-1019.

On IBM clusters the tags can vary they should be transferred as a pytest argument like so:

--tc=vlans:861,978,1138
