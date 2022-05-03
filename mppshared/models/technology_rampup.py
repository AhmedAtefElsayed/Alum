""" Class that describes the ramp-up of a technology to be used as a model constraint."""

import pandas as pd
import numpy as np

from mppshared.config import START_YEAR, END_YEAR

class TechnologyRampup:
    """ Describes an approximately exponential ramp-up trajectory for a technology with a maximum number of discrete asset additions per year. 
    The ramp-up either needs to fulfill a limit on discrete asset additions or on capacity growth."""

    def __init__(self, technology: str, start_year: int, end_year: int, maximum_asset_additions: int, maximum_capacity_growth_rate: float):
        """_summary_

        Args:
            technology (str): technology to be ramped-up
            start_year (int): Start year for technology ramp-up (year of technology maturity)
            end_year (int): _End year for technology ramp-up
            maximum_asset_additions (int): Maximum number of assets that can be added in a given year
            maximum_capacity_growth_rate (float): Maximum rate at which installed capacity can grow from one year to the next
        """

        self.technology = technology
        self.start_year = start_year 
        self.end_year = end_year  
        self.maximum_asset_additions = maximum_asset_additions  
        self.maximum_capacity_growth_rate = maximum_capacity_growth_rate  
        self.df_rampup = self.create_rampup_df(start_year, end_year, maximum_asset_additions, maximum_capacity_growth_rate)

    def create_rampup_df(self, start_year: int, end_year: int, maximum_asset_additions: int, maximum_capacity_growth_rate: float):
        """Create DataFrame indexed by year with maximum number of asset additions."""

        df_rampup = pd.DataFrame(index=np.arange(START_YEAR, END_YEAR+1), columns=["maximum_asset_number", "discrete_asset_additions", "growth_rate_asset_additions"])

        # Zero assets before start year
        df_rampup.loc[START_YEAR:start_year-1, "maximum_asset_number"] = 0
        df_rampup.loc[start_year, "discrete_asset_additions"] = maximum_asset_additions
        df_rampup.loc[start_year, "growth_rate_asset_additions"] = 0

        # Maximum asset number needs to fulfill both constraints on maximum discrete asset additions and maximum capacity growth rate 
        for year in np.arange(start_year+1, end_year+2):
            df_rampup.loc[year-1, "maximum_asset_number"] = max(
                df_rampup.loc[year-1, "discrete_asset_additions"], df_rampup.loc[year-1, "growth_rate_asset_additions"]
            )
            df_rampup.loc[year, "discrete_asset_additions"] = df_rampup.loc[year-1, "discrete_asset_additions"] + maximum_asset_additions
            df_rampup.loc[year, "growth_rate_asset_additions"] = df_rampup.loc[year-1, "maximum_asset_number"] * (1+maximum_capacity_growth_rate)
        
        df_rampup["maximum_asset_number"] = df_rampup["maximum_asset_number"].apply(lambda x: np.floor(x))
        return df_rampup["maximum_asset_number"]
