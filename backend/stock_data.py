"""Stock universe data for Indian markets"""

STOCK_UNIVERSE = [
    # ==================== IT Sector ====================
    {"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "IT"},
    {"symbol": "INFY", "name": "Infosys Ltd", "sector": "IT"},
    {"symbol": "WIPRO", "name": "Wipro Ltd", "sector": "IT"},
    {"symbol": "HCLTECH", "name": "HCL Technologies", "sector": "IT"},
    {"symbol": "TECHM", "name": "Tech Mahindra", "sector": "IT"},
    {"symbol": "LTIM", "name": "LTIMindtree Ltd", "sector": "IT"},
    {"symbol": "PERSISTENT", "name": "Persistent Systems", "sector": "IT"},
    {"symbol": "COFORGE", "name": "Coforge Ltd", "sector": "IT"},
    {"symbol": "MPHASIS", "name": "Mphasis Ltd", "sector": "IT"},
    {"symbol": "LTTS", "name": "L&T Technology Services", "sector": "IT"},

    # ==================== Banking Sector ====================
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "sector": "Banking"},
    {"symbol": "ICICIBANK", "name": "ICICI Bank", "sector": "Banking"},
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Banking"},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank", "sector": "Banking"},
    {"symbol": "AXISBANK", "name": "Axis Bank", "sector": "Banking"},
    {"symbol": "INDUSINDBK", "name": "IndusInd Bank", "sector": "Banking"},
    {"symbol": "BANDHANBNK", "name": "Bandhan Bank", "sector": "Banking"},
    {"symbol": "PNB", "name": "Punjab National Bank", "sector": "Banking"},
    {"symbol": "BANKBARODA", "name": "Bank of Baroda", "sector": "Banking"},
    {"symbol": "FEDERALBNK", "name": "Federal Bank", "sector": "Banking"},
    {"symbol": "IDFCFIRSTB", "name": "IDFC First Bank", "sector": "Banking"},
    {"symbol": "CANBK", "name": "Canara Bank", "sector": "Banking"},

    # ==================== Financial Services ====================
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance", "sector": "Financial Services"},
    {"symbol": "BAJAJFINSV", "name": "Bajaj Finserv", "sector": "Financial Services"},
    {"symbol": "HDFCLIFE", "name": "HDFC Life Insurance", "sector": "Financial Services"},
    {"symbol": "SBILIFE", "name": "SBI Life Insurance", "sector": "Financial Services"},
    {"symbol": "ICICIPRULI", "name": "ICICI Prudential Life", "sector": "Financial Services"},
    {"symbol": "BSE", "name": "BSE Ltd", "sector": "Financial Services"},
    {"symbol": "CDSL", "name": "Central Depository Services", "sector": "Financial Services"},
    {"symbol": "CHOLAFIN", "name": "Cholamandalam Investment", "sector": "Financial Services"},
    {"symbol": "MUTHOOTFIN", "name": "Muthoot Finance", "sector": "Financial Services"},

    # ==================== Pharma & Healthcare ====================
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical", "sector": "Pharma"},
    {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories", "sector": "Pharma"},
    {"symbol": "CIPLA", "name": "Cipla Ltd", "sector": "Pharma"},
    {"symbol": "DIVISLAB", "name": "Divi's Laboratories", "sector": "Pharma"},
    {"symbol": "AUROPHARMA", "name": "Aurobindo Pharma", "sector": "Pharma"},
    {"symbol": "BIOCON", "name": "Biocon Ltd", "sector": "Pharma"},
    {"symbol": "APOLLOHOSP", "name": "Apollo Hospitals Enterprise", "sector": "Healthcare"},
    {"symbol": "MAXHEALTH", "name": "Max Healthcare Institute", "sector": "Healthcare"},
    {"symbol": "LALPATHLAB", "name": "Dr Lal PathLabs", "sector": "Healthcare"},

    # ==================== Auto Sector ====================
    {"symbol": "TATAMOTORS", "name": "Tata Motors", "sector": "Auto"},
    {"symbol": "MARUTI", "name": "Maruti Suzuki India", "sector": "Auto"},
    {"symbol": "M&M", "name": "Mahindra & Mahindra", "sector": "Auto"},
    {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto", "sector": "Auto"},
    {"symbol": "HEROMOTOCO", "name": "Hero MotoCorp", "sector": "Auto"},
    {"symbol": "EICHERMOT", "name": "Eicher Motors", "sector": "Auto"},
    {"symbol": "TVSMOTOR", "name": "TVS Motor Company", "sector": "Auto"},
    {"symbol": "ASHOKLEY", "name": "Ashok Leyland", "sector": "Auto"},
    {"symbol": "MOTHERSON", "name": "Samvardhana Motherson", "sector": "Auto"},

    # ==================== FMCG Sector ====================
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever", "sector": "FMCG"},
    {"symbol": "ITC", "name": "ITC Ltd", "sector": "FMCG"},
    {"symbol": "NESTLEIND", "name": "Nestle India", "sector": "FMCG"},
    {"symbol": "BRITANNIA", "name": "Britannia Industries", "sector": "FMCG"},
    {"symbol": "DABUR", "name": "Dabur India", "sector": "FMCG"},
    {"symbol": "MARICO", "name": "Marico Ltd", "sector": "FMCG"},
    {"symbol": "GODREJCP", "name": "Godrej Consumer Products", "sector": "FMCG"},
    {"symbol": "COLPAL", "name": "Colgate-Palmolive India", "sector": "FMCG"},
    {"symbol": "TATACONSUM", "name": "Tata Consumer Products", "sector": "FMCG"},
    {"symbol": "VBL", "name": "Varun Beverages", "sector": "FMCG"},

    # ==================== Energy & Oil/Gas ====================
    {"symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Energy"},
    {"symbol": "ONGC", "name": "Oil & Natural Gas Corp", "sector": "Energy"},
    {"symbol": "BPCL", "name": "Bharat Petroleum", "sector": "Energy"},
    {"symbol": "IOC", "name": "Indian Oil Corporation", "sector": "Energy"},
    {"symbol": "NTPC", "name": "NTPC Ltd", "sector": "Energy"},
    {"symbol": "GAIL", "name": "GAIL India", "sector": "Energy"},
    {"symbol": "PETRONET", "name": "Petronet LNG", "sector": "Energy"},
    {"symbol": "ADANIENSO", "name": "Adani Energy Solutions", "sector": "Energy"},
    {"symbol": "ADANIGREEN", "name": "Adani Green Energy", "sector": "Energy"},
    {"symbol": "TATAPOWER", "name": "Tata Power Company", "sector": "Energy"},
    {"symbol": "POWERGRID", "name": "Power Grid Corporation", "sector": "Energy"},
    {"symbol": "NHPC", "name": "NHPC Ltd", "sector": "Energy"},

    # ==================== Metal & Mining ====================
    {"symbol": "TATASTEEL", "name": "Tata Steel", "sector": "Metal"},
    {"symbol": "JSWSTEEL", "name": "JSW Steel", "sector": "Metal"},
    {"symbol": "HINDALCO", "name": "Hindalco Industries", "sector": "Metal"},
    {"symbol": "COALINDIA", "name": "Coal India", "sector": "Metal"},
    {"symbol": "VEDL", "name": "Vedanta Ltd", "sector": "Metal"},
    {"symbol": "SAIL", "name": "Steel Authority of India", "sector": "Metal"},
    {"symbol": "NMDC", "name": "NMDC Ltd", "sector": "Metal"},
    {"symbol": "NATIONALUM", "name": "National Aluminium Co", "sector": "Metal"},

    # ==================== Infrastructure & Cement ====================
    {"symbol": "LT", "name": "Larsen & Toubro", "sector": "Infrastructure"},
    {"symbol": "ADANIPORTS", "name": "Adani Ports & SEZ", "sector": "Infrastructure"},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement", "sector": "Cement"},
    {"symbol": "GRASIM", "name": "Grasim Industries", "sector": "Infrastructure"},
    {"symbol": "AMBUJACEM", "name": "Ambuja Cements", "sector": "Cement"},
    {"symbol": "SHREECEM", "name": "Shree Cement", "sector": "Cement"},
    {"symbol": "ACC", "name": "ACC Ltd", "sector": "Cement"},

    # ==================== Capital Goods & Defence ====================
    {"symbol": "BHEL", "name": "Bharat Heavy Electricals", "sector": "Capital Goods"},
    {"symbol": "HAL", "name": "Hindustan Aeronautics", "sector": "Defence"},
    {"symbol": "BEL", "name": "Bharat Electronics", "sector": "Defence"},
    {"symbol": "SIEMENS", "name": "Siemens Ltd", "sector": "Capital Goods"},
    {"symbol": "ABB", "name": "ABB India", "sector": "Capital Goods"},
    {"symbol": "CUMMINSIND", "name": "Cummins India", "sector": "Capital Goods"},

    # ==================== Telecom ====================
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel", "sector": "Telecom"},
    {"symbol": "IDEA", "name": "Vodafone Idea", "sector": "Telecom"},
    {"symbol": "TATACOMM", "name": "Tata Communications", "sector": "Telecom"},

    # ==================== Consumer & Retail ====================
    {"symbol": "TITAN", "name": "Titan Company", "sector": "Consumer"},
    {"symbol": "TRENT", "name": "Trent Ltd", "sector": "Consumer"},
    {"symbol": "DMART", "name": "Avenue Supermarts", "sector": "Consumer"},
    {"symbol": "PAGEIND", "name": "Page Industries", "sector": "Consumer"},
    {"symbol": "ZOMATO", "name": "Zomato Ltd", "sector": "Consumer"},

    # ==================== Chemicals & Specialty ====================
    {"symbol": "PIDILITIND", "name": "Pidilite Industries", "sector": "Chemicals"},
    {"symbol": "SRF", "name": "SRF Ltd", "sector": "Chemicals"},
    {"symbol": "DEEPAKNTR", "name": "Deepak Nitrite", "sector": "Chemicals"},
    {"symbol": "ATUL", "name": "Atul Ltd", "sector": "Chemicals"},

    # ==================== Green Energy & Renewables ====================
    {"symbol": "SUZLON", "name": "Suzlon Energy", "sector": "Green Energy"},
    {"symbol": "IREDA", "name": "Indian Renewable Energy Dev Agency", "sector": "Green Energy"},

    # ==================== Shipping & Logistics ====================
    {"symbol": "GESHIP", "name": "Great Eastern Shipping", "sector": "Shipping"},
    {"symbol": "CONCOR", "name": "Container Corp of India", "sector": "Logistics"},

    # ==================== Realty ====================
    {"symbol": "DLF", "name": "DLF Ltd", "sector": "Realty"},
    {"symbol": "GODREJPROP", "name": "Godrej Properties", "sector": "Realty"},
    {"symbol": "OBEROIRLTY", "name": "Oberoi Realty", "sector": "Realty"},
    {"symbol": "PRESTIGE", "name": "Prestige Estates Projects", "sector": "Realty"},

    # ==================== Conglomerate / Diversified ====================
    {"symbol": "ADANIENT", "name": "Adani Enterprises", "sector": "Conglomerate"},
    {"symbol": "JSWENERGY", "name": "JSW Energy", "sector": "Energy"},

    # ==================== ETFs ====================
    {"symbol": "GOLDBEES", "name": "Nippon India ETF Gold BeES", "sector": "ETF"},
    {"symbol": "SILVERBEES", "name": "Nippon India Silver ETF", "sector": "ETF"},
    {"symbol": "NIFTYBEES", "name": "Nippon India ETF Nifty BeES", "sector": "ETF"},
    {"symbol": "BANKBEES", "name": "Nippon India ETF Bank BeES", "sector": "ETF"},
    {"symbol": "JUNIORBEES", "name": "Nippon India ETF Junior BeES", "sector": "ETF"},
    {"symbol": "CPSEETF", "name": "Nippon India ETF CPSE", "sector": "ETF"},
    {"symbol": "ITBEES", "name": "Nippon India ETF IT", "sector": "ETF"},
    {"symbol": "LIQUIDBEES", "name": "Nippon India ETF Liquid BeES", "sector": "ETF"},
    {"symbol": "MOM50", "name": "Motilal Oswal Nifty Midcap 50 ETF", "sector": "ETF"},
    {"symbol": "SETFNIF50", "name": "SBI ETF Nifty 50", "sector": "ETF"},
    {"symbol": "SETFGOLD", "name": "SBI ETF Gold", "sector": "ETF"},
]
