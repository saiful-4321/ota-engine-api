from enum import Enum

class ModifyOrderStatus(str, Enum):
    Accepted = 'Accepted'
    Partially_Filled = 'Partially Filled'
    Private_Order = 'Private Order'
    Replaced = 'Replaced'
    Unplaced = 'Unplaced'

class ModifyOrderExecStatus(str, Enum):
    Accepted = 'Accepted', 
    Replaced = 'Replaced', 
    Executed = 'Trade Executed'