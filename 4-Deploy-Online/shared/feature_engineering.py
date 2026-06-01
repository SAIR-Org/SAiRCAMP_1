"""Transform 8 raw TLC columns into 23 model-ready features."""
import math
import numpy as np
import pandas as pd
import logging
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import RobustScaler
from sklearn.pipeline import Pipeline


logger = logging.getLogger(__name__)

# Official TLC airport zone IDs — stable, documented
AIRPORT_ZONES = {1, 132, 138}  # EWR, JFK, LGA

# NYC TLC taxi zone centroids — EPSG:2263 (NY State Plane, US survey feet)
# Source: taxi_zones.shp from d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip
# Centroid = mean of polygon vertices. Distance: sqrt((x2-x1)^2+(y2-y1)^2)/5280 ≈ miles
ZONE_CENTROIDS = {
    1: (935921.0, 190798.9), 2: (1034880.4, 162357.3), 3: (1026705.0, 254200.6),
    4: (991121.6, 202996.8), 5: (931508.2, 142146.6), 6: (964326.5, 158288.2),
    7: (1006587.9, 216697.8), 8: (1005466.0, 222760.7), 9: (1042382.7, 212701.8),
    10: (1042410.0, 186334.6), 11: (981744.6, 158853.5), 12: (979958.6, 195067.6),
    13: (979446.6, 197737.4), 14: (976131.5, 167053.6), 15: (1045554.3, 227535.3),
    16: (1048526.2, 217274.8), 17: (998027.9, 191540.0), 18: (1014843.1, 255852.3),
    19: (1059390.0, 207057.5), 20: (1015960.0, 252233.6), 21: (986904.8, 156738.3),
    22: (985416.5, 161080.7), 23: (931349.1, 159615.8), 24: (993181.5, 231813.9),
    25: (988152.3, 189419.2), 26: (987594.4, 169071.5), 27: (1014586.5, 143791.9),
    28: (1037759.6, 198850.7), 29: (995220.3, 150564.5), 30: (1033429.0, 158972.3),
    31: (1018792.4, 252736.5), 32: (1021477.0, 253398.4), 33: (985497.4, 193199.4),
    34: (991410.3, 195290.8), 35: (1009127.5, 181198.9), 36: (1007310.7, 194046.8),
    37: (1005347.3, 192662.3), 38: (1057587.7, 192632.5), 39: (1014303.6, 173368.5),
    40: (985186.0, 186253.5), 41: (997933.9, 231965.2), 42: (1001664.8, 240357.6),
    43: (993527.8, 224002.9), 44: (918269.7, 132437.3), 45: (984790.8, 198520.1),
    46: (1043495.5, 249125.3), 47: (1011787.8, 246498.6), 48: (986814.1, 216674.7),
    49: (994959.6, 190757.2), 50: (984949.7, 219020.7), 51: (1031161.2, 258303.3),
    52: (985292.8, 189394.2), 53: (1025496.3, 224667.3), 54: (983209.7, 189748.3),
    55: (987592.5, 148907.3), 56: (1023985.4, 209199.5), 57: (1024887.1, 213318.5),
    58: (1035376.7, 246819.0), 59: (1013290.1, 244584.4), 60: (1016506.8, 243609.4),
    61: (1002119.2, 185248.7), 62: (999139.6, 182001.8), 63: (1016264.9, 187386.6),
    64: (1053883.6, 217225.5), 65: (988343.5, 192801.2), 66: (987664.1, 195447.0),
    67: (980073.8, 164224.4), 68: (984096.6, 211884.5), 69: (1007736.2, 241892.4),
    70: (1021406.2, 217386.4), 71: (1002023.1, 173457.8), 72: (1006037.0, 177043.8),
    73: (1037675.9, 213653.8), 74: (1002518.6, 232417.5), 75: (1000344.4, 226465.1),
    76: (1018784.6, 177869.7), 77: (1013410.9, 182340.6), 78: (1017119.4, 246712.6),
    79: (987995.4, 204054.9), 80: (1003427.3, 199796.5), 81: (1030975.8, 260534.3),
    82: (1017638.1, 207883.7), 83: (1013935.3, 208128.6), 84: (930715.5, 128977.1),
    85: (997601.4, 174561.4), 86: (1051572.9, 158955.9), 87: (982711.1, 195993.0),
    88: (980975.2, 194769.2), 89: (994769.2, 171348.3), 90: (985139.9, 209676.0),
    91: (1003853.1, 168125.9), 92: (1031992.8, 216314.7), 93: (1026950.4, 211655.9),
    94: (1012209.2, 252137.4), 95: (1027273.7, 202096.2), 96: (1021901.6, 194264.2),
    97: (990458.4, 191237.2), 98: (1046635.6, 206031.8), 99: (927800.2, 146363.2),
    100: (987376.3, 213755.9), 101: (1063051.7, 211373.6), 102: (1018336.3, 194986.2),
    103: (971556.4, 190785.8), 104: (972996.6, 194121.8), 105: (979546.9, 190666.4),
    106: (986504.1, 184768.5), 107: (988609.4, 207678.9), 108: (987410.7, 152977.2),
    109: (944361.9, 137157.3), 110: (948122.5, 136173.1), 111: (986840.9, 177211.0),
    112: (997963.9, 206839.2), 113: (985856.8, 205930.2), 114: (985091.5, 204373.5),
    115: (960798.4, 164777.7), 116: (997886.1, 240914.7), 117: (1042203.3, 156786.3),
    118: (948578.7, 153727.7), 119: (1004653.2, 244569.3), 120: (1003251.2, 247090.6),
    121: (1038197.1, 204696.9), 122: (1049672.3, 198195.0), 123: (994044.7, 157242.4),
    124: (1026598.5, 178077.1), 125: (981778.8, 203690.6), 126: (1014942.9, 233441.0),
    127: (1007074.0, 253555.1), 128: (1005992.7, 257948.4), 129: (1015504.3, 215994.2),
    130: (1042327.1, 196611.3), 131: (1045836.8, 201504.7), 132: (1044269.3, 172181.4),
    133: (990769.1, 172713.8), 134: (1030932.4, 197467.0), 135: (1033896.7, 204512.2),
    136: (1009762.7, 254479.2), 137: (991504.7, 208109.0), 138: (1019474.9, 221520.1),
    139: (1054962.5, 185926.2), 140: (996516.2, 217591.7), 141: (995299.1, 218215.3),
    142: (989153.7, 220287.7), 143: (987001.5, 222138.3), 144: (985171.6, 201945.5),
    145: (996752.6, 209798.4), 146: (1002039.8, 213665.1), 147: (1012325.3, 237948.0),
    148: (986684.3, 200960.7), 149: (999121.2, 159904.8), 150: (1000574.8, 151046.0),
    151: (992276.4, 230513.0), 152: (996391.9, 237897.3), 153: (1008637.3, 257919.2),
    154: (1007927.4, 155904.0), 155: (1011459.5, 162714.9), 156: (935981.5, 172780.9),
    157: (1010882.3, 202883.0), 158: (981344.1, 207747.9), 159: (1008205.1, 237997.4),
    160: (1016689.0, 201375.2), 161: (990525.1, 215347.3), 162: (991834.2, 214897.5),
    163: (990134.5, 218191.8), 164: (988476.1, 211987.4), 165: (995848.0, 165786.9),
    166: (994322.8, 234628.5), 167: (1010536.3, 240105.0), 168: (1008593.3, 232302.9),
    169: (1010157.1, 248294.8), 170: (990261.8, 211601.8), 171: (1037549.1, 219157.1),
    172: (955182.2, 146558.5), 173: (1022633.6, 214075.0), 174: (1016877.1, 259421.0),
    175: (1052067.7, 210301.7), 176: (950531.3, 144982.4), 177: (1008650.9, 185963.0),
    178: (992161.0, 164376.0), 179: (1003604.5, 220688.9), 180: (1026265.1, 185709.8),
    181: (989612.0, 183647.7), 182: (1023367.5, 244285.1), 183: (1030976.7, 248770.5),
    184: (1040525.4, 253480.0), 185: (1024928.3, 250581.8), 186: (986466.8, 212006.4),
    187: (946465.7, 169817.8), 188: (998652.2, 179278.4), 189: (993089.8, 185821.2),
    190: (991860.4, 180120.0), 191: (1055651.3, 200578.4), 192: (1035609.4, 210412.9),
    193: (1001122.3, 217170.3), 194: (1004812.7, 227770.2), 195: (980635.2, 184995.9),
    196: (1021957.0, 203869.4), 197: (1031641.6, 192707.0), 198: (1010819.5, 197001.4),
    199: (1017288.0, 228389.0), 200: (1009632.7, 266802.8), 201: (1029182.5, 150173.7),
    202: (998042.8, 216811.5), 203: (1055036.7, 174039.2), 204: (926202.1, 136054.5),
    205: (1049619.7, 191797.8), 206: (956513.6, 172665.2), 207: (1012601.6, 217553.6),
    208: (1035495.8, 238137.9), 209: (983621.6, 197319.5), 210: (1003653.6, 154238.5),
    211: (983642.8, 202871.2), 212: (1020734.8, 240955.4), 213: (1025668.9, 236366.7),
    214: (962224.9, 152026.1), 215: (1041908.8, 192458.7), 216: (1034973.9, 185788.1),
    217: (995884.6, 195786.2), 218: (1047284.5, 184525.2), 219: (1047949.0, 180530.7),
    220: (1008570.2, 260734.2), 221: (964208.8, 165334.4), 222: (1016405.4, 174206.8),
    223: (1013134.9, 224226.4), 224: (991365.8, 205827.2), 225: (1003532.8, 190209.8),
    226: (1004805.8, 204151.1), 227: (982345.1, 172355.4), 228: (980934.6, 178085.3),
    229: (994145.1, 214631.3), 230: (988595.7, 216022.3), 231: (981511.2, 201172.4),
    232: (988975.4, 199258.5), 233: (992683.5, 211175.0), 234: (986984.9, 208627.2),
    235: (1007167.1, 250471.8), 236: (996120.4, 223550.6), 237: (993760.3, 219247.9),
    238: (991430.9, 227966.2), 239: (988910.6, 225197.9), 240: (1017681.6, 263843.7),
    241: (1013019.1, 258205.8), 242: (1025962.3, 248450.2), 243: (1001533.6, 251647.9),
    244: (999950.3, 246355.5), 245: (955439.9, 169674.6), 246: (982002.6, 212560.2),
    247: (1005260.8, 241762.9), 248: (1019210.3, 243465.2), 249: (983396.0, 206623.6),
    250: (1027152.5, 243289.5), 251: (949248.3, 163910.5), 252: (1035477.0, 229006.7),
    253: (1027963.6, 216949.8), 254: (1023224.2, 260788.8), 255: (994874.4, 201467.3),
    256: (994524.3, 198219.0), 257: (990235.9, 178288.1), 258: (1024537.6, 189835.9),
    259: (1024712.4, 267245.4), 260: (1010321.8, 211238.4), 261: (980373.2, 197021.9),
    262: (999901.0, 222860.5), 263: (998042.6, 223098.7),
}

# Precompute numpy arrays for vectorized centroid lookup (faster than dict in transform)
# Size 266 covers all zone IDs 1-265 with a spare slot.
_MAX_ZONE = 266
_CX = np.zeros(_MAX_ZONE)
_CY = np.zeros(_MAX_ZONE)
for _z, (_x, _y) in ZONE_CENTROIDS.items():
    _CX[_z] = _x
    _CY[_z] = _y
_FEET_PER_MILE = 5280.0


class TripFeatureEngineer(BaseEstimator, TransformerMixin):
    """Feature engineering for 2019+ TLC data (zone IDs, no lat/lon)."""

    def __init__(self):
        self.feature_names_ = []

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X_df = X.copy()
        X_df['tpep_pickup_datetime'] = pd.to_datetime(X_df['tpep_pickup_datetime'])

        # ── Zone ID features (replaces lat/lon distance features) ─────────────
        pu = X_df['PULocationID'].values.astype(int)
        do = X_df['DOLocationID'].values.astype(int)

        X_df['zone_pair'] = pu * 1000 + do
        X_df['is_same_zone'] = (pu == do).astype(int)
        X_df['is_airport_pickup']  = np.isin(pu, list(AIRPORT_ZONES)).astype(int)
        X_df['is_airport_dropoff'] = np.isin(do, list(AIRPORT_ZONES)).astype(int)
        X_df['is_airport_trip'] = (
            X_df['is_airport_pickup'] | X_df['is_airport_dropoff']
        )

        # ── Zone centroid features — recovers geometric signal lost from lat/lon ──
        # Coordinates in EPSG:2263 (NY State Plane, US survey feet).
        # centroid_distance_miles: Euclidean distance between pickup/dropoff zone
        #   centroids. Equivalent to haversine_distance in the 2016 pipeline.
        # centroid_direction_sin/cos: cyclical encoding of travel direction.
        #   Captures rush-hour asymmetry: same corridor, opposite direction →
        #   different duration (e.g., inbound vs outbound Manhattan).
        pu_cx, pu_cy = _CX[pu], _CY[pu]
        do_cx, do_cy = _CX[do], _CY[do]
        dx = do_cx - pu_cx
        dy = do_cy - pu_cy
        dist_ft = np.sqrt(dx ** 2 + dy ** 2)
        X_df['centroid_distance_miles'] = dist_ft / _FEET_PER_MILE
        angle = np.arctan2(dy, dx)
        X_df['centroid_direction_sin'] = np.sin(angle)
        X_df['centroid_direction_cos'] = np.cos(angle)

        # efficiency_ratio: actual trip miles / centroid straight-line miles.
        # > 1 means the driver took a longer route than the zone-to-zone straight line.
        # Captures detours, traffic rerouting, and airport loop roads.
        # +0.1 avoids division by zero on same-zone trips (centroid_distance ≈ 0).
        X_df['efficiency_ratio'] = (
            X_df['trip_distance'] / (X_df['centroid_distance_miles'] + 0.1)
        )

        # ── Temporal features (unchanged) ─────────────────────────────────────
        X_df['pickup_hour']      = X_df['tpep_pickup_datetime'].dt.hour
        X_df['pickup_dayofweek'] = X_df['tpep_pickup_datetime'].dt.dayofweek
        X_df['pickup_month']     = X_df['tpep_pickup_datetime'].dt.month

        # Cyclical encoding (unchanged)
        X_df['hour_sin']       = np.sin(2 * np.pi * X_df['pickup_hour'] / 24)
        X_df['hour_cos']       = np.cos(2 * np.pi * X_df['pickup_hour'] / 24)
        X_df['dayofweek_sin']  = np.sin(2 * np.pi * X_df['pickup_dayofweek'] / 7)
        X_df['dayofweek_cos']  = np.cos(2 * np.pi * X_df['pickup_dayofweek'] / 7)

        # Time flags (unchanged)
        X_df['is_rush_hour'] = (
            (X_df['pickup_hour'].between(7, 9)) |
            (X_df['pickup_hour'].between(16, 18))
        ).astype(int)
        X_df['is_weekend'] = X_df['pickup_dayofweek'].isin([5, 6]).astype(int)

        # ── Categorical encoding (unchanged) ──────────────────────────────────
        X_df['is_vendor_2']    = (X_df['VendorID'] == 2).astype(int)
        X_df['is_credit_card'] = (X_df['payment_type'] == 1).astype(int)

        # ── Interaction feature (unchanged) ───────────────────────────────────
        X_df['distance_times_passengers'] = (
            X_df['trip_distance'] * X_df['passenger_count']
        )

        # ── Drop raw columns ──────────────────────────────────────────────────
        cols_to_drop = [
            'tpep_pickup_datetime',
            'PULocationID', 'DOLocationID',
            'VendorID', 'RatecodeID', 'payment_type',
        ]
        X_df = X_df.drop(columns=cols_to_drop, errors='ignore')

        numeric_cols = X_df.select_dtypes(include=[np.number]).columns.tolist()
        self.feature_names_ = numeric_cols

        return X_df[numeric_cols].values

    def get_feature_names(self):
        return self.feature_names_


class OutlierHandler(BaseEstimator, TransformerMixin):
    """IQR-based outlier handling — identical to pipeline_with_prefect."""

    def __init__(self, factor=1.5):
        self.factor = factor
        self.lower_bounds_ = None
        self.upper_bounds_ = None

    def fit(self, X, y=None):
        self.lower_bounds_, self.upper_bounds_ = [], []
        for i in range(X.shape[1]):
            Q1 = np.percentile(X[:, i], 25)
            Q3 = np.percentile(X[:, i], 75)
            IQR = Q3 - Q1
            self.lower_bounds_.append(Q1 - self.factor * IQR)
            self.upper_bounds_.append(Q3 + self.factor * IQR)
        return self

    def transform(self, X):
        X_t = X.copy()
        for i in range(X.shape[1]):
            X_t[:, i] = np.clip(X_t[:, i], self.lower_bounds_[i], self.upper_bounds_[i])
        return X_t


def build_preprocessor(iqr_factor: float = 1.5) -> Pipeline:
    """Build preprocessing pipeline — identical structure to pipeline_with_prefect."""
    return Pipeline([
        ('feature_engineer', TripFeatureEngineer()),
        ('outlier_handler',  OutlierHandler(factor=iqr_factor)),
        ('scaler',           RobustScaler()),
    ])
