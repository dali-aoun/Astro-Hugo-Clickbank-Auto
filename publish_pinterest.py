"""
publish_pinterest.py â€” Pinterest educational content publisher
Strategy: informational tips/facts per board â†’ saves â†’ organic reach â†’ bio link clicks
Images generated on-the-fly with Pillow, uploaded as base64 directly to Pinterest API v5
3 pins per day, rotating across boards and content library
"""

import os, sys, json, time, base64, io, random, traceback, subprocess, asyncio, tempfile
from PIL import Image, ImageDraw, ImageFont
from datetime import date, datetime, timezone, timedelta

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DONE_FILE = os.path.join(BASE_DIR, "pinterest_done.json")
LOG_FILE  = os.path.join(BASE_DIR, "pinterest_log.txt")
IDX_FILE       = os.path.join(BASE_DIR, "pinterest_idx.json")
VIDEO_IDX_FILE = os.path.join(BASE_DIR, "pinterest_video_idx.json")

PINTEREST_TOKEN = os.environ.get("PINTEREST_ACCESS_TOKEN", "")
SITE_URL = "https://reviews.thehappy-healthy-life.com"

PINS_PER_DAY = 5
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# â”€â”€ Board map â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BOARDS = {
    "dental":   {"id": "1140677480561291808", "name": "Dental Health Reviews",    "accent": (16, 185, 129),  "cat_url": "dental-health"},
    "prostate": {"id": "1140677480561291810", "name": "Prostate Health Reviews",  "accent": (59, 130, 246),  "cat_url": "prostate-health"},
    "male":     {"id": "1140677480561291813", "name": "Male Performance Reviews", "accent": (239, 68, 68),   "cat_url": "male-performance"},
    "brain":    {"id": "1140677480561291815", "name": "Brain & Cognitive Health", "accent": (139, 92, 246),  "cat_url": "brain-and-senses"},
    "weight":   {"id": "1140677480561291817", "name": "Weight Loss Supplements",  "accent": (245, 158, 11),  "cat_url": "weight-loss"},
    "beauty":   {"id": "1140677480561291819", "name": "Beauty & Skin Care",       "accent": (236, 72, 153),  "cat_url": "beauty-skin"},
    "womens":   {"id": "1140677480561291820", "name": "Women's Health Reviews",   "accent": (168, 85, 247),  "cat_url": "womens-health"},
    "blood":    {"id": "1140677480561291821", "name": "Blood Sugar Support",      "accent": (6, 182, 212),   "cat_url": "blood-sugar"},
    "joint":    {"id": "1140677480561291822", "name": "Joint Pain Relief",        "accent": (20, 184, 166),  "cat_url": "joint-pain"},
    "sleep":    {"id": "1140677480561291823", "name": "Sleep Supplements",        "accent": (99, 102, 241),  "cat_url": "sleep"},
    "heart":    {"id": "1140677480561291834", "name": "Heart Health Reviews",     "accent": (244, 63, 94),   "cat_url": "heart-health"},
    "general":  {"id": "1140677480561291839", "name": "General Health Reviews",   "accent": (34, 197, 94),   "cat_url": "general-health"},
}

# Map product category slug → BOARDS key
CAT_TO_BOARD = {
    "dental-health":    "dental",
    "prostate-health":  "prostate",
    "male-performance": "male",
    "brain-and-senses": "brain",
    "weight-loss":      "weight",
    "beauty-skin":      "beauty",
    "womens-health":    "womens",
    "blood-sugar":      "blood",
    "joint-pain":       "joint",
    "heart-health":     "heart",
    "general-health":   "general",
}

# Board rotation order (balanced across categories)
BOARD_ROTATION = [
    "dental", "weight", "brain", "prostate", "beauty", "heart",
    "male", "blood", "sleep", "joint", "womens", "general",
]

# â”€â”€ Content library â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Each item: (headline, body, hashtags)
CONTENT = {
    "dental": [
        ("Did You Know?", "Your mouth contains over 700 species of bacteria.\nMost are harmless â€” but the bad ones cause gum disease, cavities, and bad breath.", "#OralHealth #DentalTips #GumHealth"),
        ("Warning Sign", "Bleeding gums when you brush is NOT normal.\nIt's an early sign of gingivitis â€” and it's reversible if you act now.", "#GumDisease #DentalHealth #OralCare"),
        ("Fact", "Gum disease is linked to heart disease, diabetes, and Alzheimer's.\nYour oral health affects your whole body.", "#OralHealth #HeartHealth #DentalFacts"),
        ("Daily Tip", "The best time to brush is 30 minutes AFTER eating.\nBrushing immediately after meals can damage enamel softened by acids.", "#BrushingTips #DentalCare #ToothCare"),
        ("Statistic", "47% of adults over 30 have some form of gum disease.\nThe earlier you treat it, the easier it is to reverse.", "#GumHealth #DentalFacts #OralCare"),
        ("Did You Know?", "Your tongue holds more bacteria than any other part of your mouth.\nCleaning it daily can eliminate up to 70% of bad breath.", "#BadBreath #OralHygiene #DentalTips"),
        ("Tip", "Oil pulling with coconut oil for 10â€“15 minutes reduces harmful bacteria by up to 30%.\nAncient practice, modern science confirms it.", "#OilPulling #NaturalDental #OralHealth"),
        ("Warning", "Dry mouth is a silent tooth destroyer.\nSaliva neutralizes acids and remineralizes enamel â€” without it, cavities accelerate.", "#DryMouth #DentalHealth #ToothDecay"),
        ("Fact", "Vitamin D deficiency is directly linked to higher rates of tooth decay.\nYour teeth need vitamins too.", "#VitaminD #DentalNutrition #OralHealth"),
        ("Statistic", "Americans spend $124 billion on dental care each year.\nMost problems are preventable with daily habits.", "#PreventiveDental #OralCare #DentalFacts"),
        ("Tip", "Flossing removes plaque from 35% of tooth surfaces that your brush can't reach.\nSkip floss, skip a third of your mouth.", "#Flossing #DentalTips #OralHygiene"),
        ("Did You Know?", "Sugar doesn't directly rot your teeth.\nBacteria eat the sugar and produce acid â€” the acid is what destroys enamel.", "#SugarAndTeeth #DentalFacts #OralHealth"),
        ("Warning", "Grinding your teeth at night can wear down enamel by up to 0.2mm per year.\nOver a decade, that's irreversible damage.", "#TeethGrinding #Bruxism #DentalHealth"),
        ("Fact", "Probiotics for oral health are the new frontier.\nCertain strains of beneficial bacteria outcompete the harmful ones in your mouth.", "#OralProbiotics #DentalHealth #NaturalOralCare"),
        ("Tip", "Green tea contains catechins that reduce inflammation and kill oral bacteria.\nSwap one coffee for green tea daily.", "#GreenTea #OralHealth #NaturalDental"),
        ("Statistic", "People who smoke are 2x more likely to develop gum disease than non-smokers.\nSmoking reduces blood flow to gum tissue.", "#GumDisease #OralHealth #DentalFacts"),
        ("Did You Know?", "Your enamel is the hardest substance in your body â€” harder than bone.\nBut once it's gone, it doesn't grow back.", "#ToothEnamel #DentalFacts #OralCare"),
        ("Tip", "Crunchy vegetables like celery and carrots naturally clean teeth.\nThey increase saliva flow and scrub away plaque.", "#NaturalDental #HealthyTeeth #OralCare"),
        ("Fact", "Stress causes dry mouth, teeth grinding, and gum inflammation.\nYour mental health directly impacts your oral health.", "#StressAndHealth #OralHealth #DentalCare"),
        ("Warning", "Many mouthwashes with alcohol kill good bacteria too.\nLook for alcohol-free formulas that preserve your oral microbiome.", "#Mouthwash #OralMicrobiome #DentalTips"),
    ],
    "weight": [
        ("Fact", "Your gut microbiome controls up to 30% of how many calories you absorb.\nA healthy gut means better weight management.", "#GutHealth #WeightLoss #Microbiome"),
        ("Did You Know?", "Sleeping less than 6 hours per night increases hunger hormones by 28%.\nPoor sleep makes weight loss nearly impossible.", "#SleepAndWeight #WeightLoss #HealthyHabits"),
        ("Tip", "Drinking 500ml of water 30 minutes before meals reduces calorie intake by 13%.\nHydration is a free weight loss tool.", "#HydrationTips #WeightLoss #HealthyHabits"),
        ("Statistic", "People who eat breakfast lose 17% more weight than breakfast skippers.\nDon't skip your morning meal.", "#BreakfastTips #WeightLoss #Metabolism"),
        ("Warning", "\"Diet\" drinks still spike insulin and increase cravings.\nArtificial sweeteners can make weight loss harder, not easier.", "#DietDrinks #WeightLossMyths #HealthFacts"),
        ("Fact", "Protein requires 25â€“30% of its own calories to be digested.\nEating more protein literally boosts your metabolism.", "#ProteinDiet #WeightLoss #MetabolismBoost"),
        ("Did You Know?", "Stress triggers cortisol, which directs your body to store fat around the belly.\nManaging stress is a weight loss strategy.", "#StressBelly #CortisolWeight #WeightLoss"),
        ("Tip", "A 10-minute walk after eating reduces blood sugar spikes by 22%.\nThis simple habit prevents fat storage.", "#PostMealWalk #BloodSugar #WeightLoss"),
        ("Statistic", "70% of your weight loss results come from what you eat.\nExercise alone rarely works without diet changes.", "#WeightLossFacts #DietVsExercise #HealthyEating"),
        ("Warning", "Skipping meals slows your metabolism by up to 30%.\nYour body goes into starvation mode and holds onto fat.", "#SkippingMeals #MetabolismMyths #WeightLoss"),
        ("Fact", "Green tea extract increases fat burning by 17% during exercise.\nThe EGCG compound activates fat oxidation enzymes.", "#GreenTeaExtract #FatBurner #WeightLoss"),
        ("Did You Know?", "Cold exposure activates brown fat â€” the type that burns calories for heat.\nCold showers can burn an extra 50â€“100 calories per session.", "#ColdTherapy #BrownFat #WeightLoss"),
        ("Tip", "Eating slowly and chewing thoroughly reduces calorie intake by up to 10%.\nYour brain needs 20 minutes to register fullness.", "#MindfulEating #WeightLoss #HealthyHabits"),
        ("Statistic", "People who track their food intake lose twice as much weight as those who don't.\nAwareness is the first step.", "#FoodTracking #WeightLoss #Accountability"),
        ("Fact", "Fiber expands in your stomach and slows digestion, keeping you full longer.\nAim for 25â€“35g of fiber per day.", "#FiberDiet #WeightLoss #Fullness"),
        ("Warning", "Fad diets that eliminate entire food groups cause muscle loss, not just fat loss.\nMuscle burns calories even at rest.", "#FadDiets #MusclePreservation #WeightLossMyths"),
        ("Did You Know?", "Your liver is your primary fat-burning organ.\nNon-alcoholic fatty liver is now found in 25% of adults â€” it kills metabolism.", "#LiverHealth #FatBurning #WeightLoss"),
        ("Tip", "Resistance training builds muscle that burns calories 24/7.\n2 sessions per week is enough to significantly boost resting metabolism.", "#StrengthTraining #MetabolismBoost #WeightLoss"),
        ("Fact", "Eating spicy food containing capsaicin burns an extra 50 calories per meal.\nSpice up your meals for free calorie burn.", "#Capsaicin #ThermogenicFood #WeightLoss"),
        ("Statistic", "The average person makes 200+ food-related decisions per day.\nMost are unconscious â€” your environment shapes your choices.", "#FoodChoices #WeightLoss #HealthyEnvironment"),
    ],
    "brain": [
        ("Fact", "Your brain is 60% fat by dry weight.\nThe type of fat you eat directly determines how well your brain functions.", "#BrainHealth #BrainFacts #CognitiveHealth"),
        ("Did You Know?", "You have more neural connections in your brain than stars in the Milky Way.\nBut they weaken without the right nutrients.", "#BrainFacts #Neuroscience #CognitiveHealth"),
        ("Tip", "Exercise increases BDNF (Brain-Derived Neurotrophic Factor) by up to 3x.\nBDNF is like fertilizer for brain cells.", "#BDNF #BrainExercise #CognitiveBoost"),
        ("Warning", "Chronic stress physically shrinks the hippocampus â€” your memory center.\nStress management is literally brain protection.", "#StressAndBrain #MemoryHealth #CognitiveHealth"),
        ("Statistic", "65 million people worldwide live with dementia.\nLifestyle changes in your 40s and 50s reduce risk by up to 40%.", "#DementiaPrevention #BrainHealth #CognitiveHealth"),
        ("Fact", "Omega-3 DHA makes up 40% of the polyunsaturated fatty acids in the brain.\nLow DHA = slower thinking, worse memory.", "#Omega3 #BrainNutrition #CognitiveHealth"),
        ("Did You Know?", "Your gut produces 95% of your body's serotonin.\nAn unhealthy gut means poor mood, brain fog, and anxiety.", "#GutBrainAxis #Serotonin #MentalHealth"),
        ("Tip", "Learning a new skill creates new neural pathways â€” literally changing your brain's structure.\nLearn something new every week.", "#Neuroplasticity #BrainTraining #CognitiveHealth"),
        ("Warning", "Alcohol kills brain cells and shrinks the prefrontal cortex.\nEven moderate drinking reduces brain volume over time.", "#AlcoholAndBrain #BrainHealth #CognitiveProtection"),
        ("Fact", "Sleep is when your brain clears toxic waste through the glymphatic system.\nSkipping sleep literally lets toxins build up in your brain.", "#SleepAndBrain #GlymphaticSystem #BrainDetox"),
        ("Statistic", "People with higher social connection have a 50% reduced risk of cognitive decline.\nLoneliness is as dangerous as smoking 15 cigarettes a day.", "#SocialHealth #BrainHealth #CognitiveHealth"),
        ("Did You Know?", "Blueberries contain anthocyanins that cross the blood-brain barrier.\nStudies show they improve memory by 20% in older adults.", "#Blueberries #BrainFood #CognitiveBoost"),
        ("Tip", "Meditation increases gray matter in the prefrontal cortex.\n8 weeks of 10 minutes/day is enough to measurably change brain structure.", "#Meditation #BrainHealth #Mindfulness"),
        ("Fact", "Curcumin (in turmeric) crosses the blood-brain barrier and reduces amyloid plaques.\nIt's one of the most studied brain-protective compounds.", "#Turmeric #Curcumin #BrainHealth"),
        ("Warning", "Chronic dehydration reduces brain volume and slows cognitive processing speed.\nJust 1â€“2% dehydration impairs performance.", "#DehydrationBrain #WaterAndBrain #CognitiveHealth"),
        ("Statistic", "Bilingual people develop Alzheimer's 4â€“5 years later than monolinguals.\nYour brain can be trained to be more resilient.", "#BilingualBrain #AlzheimersPrevention #BrainHealth"),
        ("Did You Know?", "The brain uses 20% of your body's energy while being only 2% of body weight.\nBrain fog often means your brain is simply under-fueled.", "#BrainFog #BrainEnergy #CognitiveHealth"),
        ("Tip", "Cold exposure releases norepinephrine in the brain, improving focus and attention by up to 300%.\nCold showers boost brain performance.", "#ColdShower #Norepinephrine #Focus"),
        ("Fact", "Magnesium deficiency impairs learning and memory in both children and adults.\n68% of Americans don't get enough magnesium.", "#MagnesiumBrain #BrainNutrition #CognitiveHealth"),
        ("Statistic", "People who read daily have a 32% lower rate of cognitive decline.\nReading is one of the best free brain exercises.", "#ReadingBrain #CognitiveHealth #BrainTraining"),
    ],
    "prostate": [
        ("Fact", "1 in 8 men will be diagnosed with prostate cancer in their lifetime.\nEarly detection is the key to survival.", "#ProstateHealth #MensHealth #ProstateCancer"),
        ("Did You Know?", "The prostate gland is only the size of a walnut â€” but it surrounds the urethra.\nWhen it swells, it affects every bathroom trip.", "#ProstateHealth #BPH #MensHealth"),
        ("Tip", "Saw palmetto has been shown in studies to reduce nighttime urination by 48%.\nIt's the most researched herb for prostate support.", "#SawPalmetto #ProstateHealth #NaturalRemedies"),
        ("Warning", "Sitting for more than 8 hours per day increases prostate inflammation risk.\nTake a 5-minute standing break every hour.", "#ProstateHealth #SittingDangers #MensHealth"),
        ("Statistic", "Prostate problems affect 50% of men over 50, and 90% of men over 80.\nStarting prevention in your 40s makes a massive difference.", "#BPH #ProstateHealth #MenOver50"),
        ("Fact", "Lycopene from cooked tomatoes reduces PSA levels and prostate cancer risk by up to 35%.\nCook your tomatoes â€” heat releases lycopene.", "#Lycopene #TomatoHealth #ProstateNutrition"),
        ("Did You Know?", "Frequent ejaculation (21+ times per month) reduces prostate cancer risk by 31%.\nThis is a real Harvard Medical School finding.", "#ProstateHealth #MensHealth #HealthFacts"),
        ("Tip", "Pumpkin seeds are rich in zinc â€” the mineral most concentrated in healthy prostate tissue.\nA handful a day supports prostate function.", "#PumpkinSeeds #Zinc #ProstateHealth"),
        ("Warning", "Red meat and dairy increase prostate cancer risk when consumed in excess.\nAim for 2 servings or less per week.", "#DietAndProstate #ProstateHealth #MensNutrition"),
        ("Fact", "Exercise reduces the risk of BPH (enlarged prostate) by up to 25%.\nJust 30 minutes of walking daily is enough.", "#ProstateExercise #BPH #MensHealth"),
        ("Statistic", "Men who drink 5+ cups of coffee per day have a 59% lower risk of lethal prostate cancer.\nCaffeine appears to slow cancer cell growth.", "#CoffeeAndProstate #ProstateHealth #MensHealth"),
        ("Did You Know?", "High DHT levels shrink prostate tissue in young men but cause it to grow in older men.\nHormonal balance is crucial for prostate health.", "#DHT #ProstateHealth #HormoneBalance"),
        ("Tip", "Green tea catechins reduce PSA levels and slow prostate cell division.\n3 cups per day shows measurable effects in studies.", "#GreenTeaProstate #PSALevels #ProstateHealth"),
        ("Warning", "Stress hormones (cortisol) worsen prostate inflammation directly.\nStress management isn't optional for men's health.", "#CortisolProstate #MensHealth #StressReduction"),
        ("Fact", "Beta-sitosterol (found in plants) improves urine flow and reduces urgency in men with BPH.\nIt works by blocking 5-alpha reductase.", "#BetaSitosterol #BPH #ProstateHealth"),
        ("Statistic", "Men who are overweight are 40% more likely to develop aggressive prostate cancer.\nBody weight directly influences prostate hormones.", "#WeightAndProstate #ProstateHealth #MensHealth"),
        ("Did You Know?", "The PSA test isn't perfect â€” 75% of high PSA results are NOT cancer.\nDiscuss your PSA score with context, not in isolation.", "#PSATest #ProstateHealth #MensHealth"),
        ("Tip", "Vitamin D3 deficiency is strongly linked to aggressive prostate cancer.\nGet your levels tested â€” optimal is 60â€“80 ng/mL.", "#VitaminDProstate #ProstateHealth #MensHealth"),
        ("Fact", "Nettle root extract reduces prostate symptoms and improves urine flow in clinical trials.\nIt's one of the most-used herbs in European urology.", "#NettleRoot #BPH #ProstateHealth"),
        ("Warning", "Antihistamines and cold medications can trigger acute urinary retention in men with BPH.\nAlways check medications if you have prostate issues.", "#BPH #ProstateHealth #MedicationWarning"),
    ],
    "beauty": [
        ("Fact", "Your skin replaces itself every 27 days.\nWhat you eat this month is literally what your skin will be made of next month.", "#SkinHealth #SkincareFacts #Beauty"),
        ("Did You Know?", "UV rays are the #1 cause of premature aging, responsible for 90% of wrinkles.\nSunscreen is the most proven anti-aging product.", "#Sunscreen #AntiAging #SkincareTips"),
        ("Tip", "Retinol stimulates collagen production and cell turnover faster than any other ingredient.\nStart at 0.025% and work up slowly.", "#Retinol #AntiAging #SkincareTips"),
        ("Warning", "Hot showers strip your skin's natural oil barrier.\nShower in lukewarm water and moisturize within 3 minutes of drying off.", "#SkinCare #HydrationTips #SkinHealth"),
        ("Statistic", "Collagen production decreases by 1% every year after age 20.\nBy 50, you've lost 30% of your skin's structural support.", "#Collagen #AntiAging #SkincareFacts"),
        ("Fact", "Your gut microbiome directly influences acne, eczema, and rosacea.\nClear skin starts in the digestive system.", "#GutSkinAxis #AcneTreatment #SkinHealth"),
        ("Did You Know?", "Silk pillowcases reduce sleep wrinkles and hair breakage significantly compared to cotton.\nSmall upgrade, big results.", "#SkincareTips #AntiAging #BeautyHacks"),
        ("Tip", "Vitamin C serum in the morning + retinol at night is the most effective anti-aging routine.\nThey work on different skin repair pathways.", "#VitaminCSerum #Retinol #SkincareTips"),
        ("Warning", "Most skincare products are 70â€“80% water and preservatives.\nThe concentration of active ingredients matters more than the brand.", "#SkincareMyths #Beauty #SkincareFacts"),
        ("Fact", "Hyaluronic acid holds up to 1000x its weight in water.\nIt's the most effective hydrating molecule for skin.", "#HyaluronicAcid #SkinHydration #SkincareFacts"),
        ("Statistic", "Women touch their face an average of 23 times per hour.\nEach touch transfers bacteria and causes breakouts.", "#TouchingFace #AcnePrevention #SkincareTips"),
        ("Did You Know?", "Sleep is when your skin regenerates â€” growth hormone peaks at night.\nMissing sleep ages your skin faster than sun exposure.", "#SleepAndSkin #AntiAging #SkinHealth"),
        ("Tip", "Niacinamide (Vitamin B3) reduces pore size, fades dark spots, and controls oil.\nIt's the most versatile skincare ingredient for any skin type.", "#Niacinamide #SkincareTips #Skincare"),
        ("Warning", "Fragrance is the #1 cause of skincare allergies and contact dermatitis.\nChoose fragrance-free products for sensitive skin.", "#FragranceFree #SensitiveSkin #Skincare"),
        ("Fact", "Ceramides make up 50% of your skin's protective barrier.\nWithout them, moisture escapes and irritants enter.", "#Ceramides #SkinBarrier #SkincareFacts"),
        ("Statistic", "People who eat 5+ servings of vegetables daily show measurably younger-looking skin at any age.\nYour plate is your skincare routine.", "#NutritionAndSkin #HealthySkin #Beauty"),
        ("Did You Know?", "The skin around your eyes is 10x thinner than the rest of your face.\nThis is why it shows aging first.", "#EyeArea #AntiAging #SkincareTips"),
        ("Tip", "Gua sha massage increases lymphatic drainage and reduces puffiness by 25% in 4 weeks.\nInclude it in your morning routine.", "#GuaSha #FaceMassage #SkincareTips"),
        ("Fact", "Astaxanthin is 6000x more powerful than Vitamin C as an antioxidant.\nIt's the compound that makes flamingos pink â€” and one of the best skin protectors.", "#Astaxanthin #AntioxidantSkin #SkincareFacts"),
        ("Warning", "Exfoliating more than 2â€“3 times per week damages your skin barrier.\nOver-exfoliation causes sensitivity and breakouts.", "#Exfoliation #SkinBarrier #SkincareTips"),
    ],
    "heart": [
        ("Fact", "Heart disease kills 1 person every 36 seconds in the US.\nIt remains the #1 killer worldwide for both men and women.", "#HeartHealth #CardiovascularHealth #HeartDisease"),
        ("Did You Know?", "Your heart beats 100,000 times per day.\nOver a lifetime, that's 2.5 billion beats â€” and it needs fuel to keep going.", "#HeartFacts #CardiovascularHealth #HeartHealth"),
        ("Tip", "Omega-3 fatty acids reduce triglycerides by up to 30% and lower heart disease risk significantly.\nAim for 2 servings of fatty fish per week.", "#Omega3 #HeartHealth #CardiovascularNutrition"),
        ("Warning", "Trans fats increase LDL cholesterol AND decrease HDL â€” doubling your heart disease risk.\nCheck labels for 'partially hydrogenated oils'.", "#TransFats #Cholesterol #HeartHealth"),
        ("Statistic", "50% of heart attacks occur in people with normal cholesterol levels.\nInflammation, not just cholesterol, is the real risk factor.", "#HeartAttack #Inflammation #CardiovascularHealth"),
        ("Fact", "Exercise reduces heart attack risk by 35% â€” more than most medications.\n150 minutes of moderate activity per week is the target.", "#ExerciseAndHeart #HeartHealth #Cardio"),
        ("Did You Know?", "Your heart has its own nervous system â€” about 40,000 neurons.\nThis is why strong emotions physically affect your heart rhythm.", "#HeartBrainConnection #HeartFacts #CardiovascularHealth"),
        ("Tip", "Dark chocolate (70%+) contains flavonoids that lower blood pressure by 5 points.\n1â€“2 squares daily is therapeutic, not indulgent.", "#DarkChocolate #HeartHealth #Flavonoids"),
        ("Warning", "Loneliness raises cortisol levels chronically, increasing heart disease risk by 29%.\nSocial connection is literally medicine for your heart.", "#LonelinessHealth #HeartHealth #StressAndHeart"),
        ("Fact", "Magnesium regulates heart rhythm and blood pressure.\nDeficiency is linked to 7x higher risk of sudden cardiac death.", "#MagnesiumHeart #HeartHealth #CardiovascularNutrition"),
        ("Statistic", "People who sleep 6â€“8 hours per night have a 48% lower risk of heart disease than those who sleep less.\nSleep is cardiovascular medicine.", "#SleepAndHeart #HeartHealth #SleepFacts"),
        ("Did You Know?", "Gum disease bacteria (P. gingivalis) have been found in arterial plaques.\nYour dental hygiene affects your heart.", "#OralHeartConnection #HeartHealth #GumDisease"),
        ("Tip", "Walking just 30 minutes per day reduces your risk of heart disease by 19%.\nYou don't need a gym â€” just consistency.", "#WalkingBenefits #HeartHealth #Cardio"),
        ("Warning", "Energy drinks spike blood pressure and can trigger arrhythmias even in healthy young adults.\nCaffeine overload stresses your heart.", "#EnergyDrinks #HeartHealth #Arrhythmia"),
        ("Fact", "CoQ10 is essential for energy production in heart muscle cells.\nStatin drugs deplete CoQ10 â€” supplementing is crucial if you're on statins.", "#CoQ10 #HeartHealth #StatinMeds"),
        ("Statistic", "Reducing sodium by just 1g per day lowers blood pressure by 5 mmHg.\nSmall dietary changes have measurable cardiovascular impact.", "#SodiumBloodPressure #HeartHealth #NutritionFacts"),
        ("Did You Know?", "Women's heart attack symptoms are often different from men's.\nNausea, jaw pain, and fatigue â€” not just chest pain.", "#WomensHeartHealth #HeartAttack #CardiovascularHealth"),
        ("Tip", "The DASH diet reduces blood pressure as effectively as medication in some people.\nFocus on fruits, vegetables, whole grains, and low-fat dairy.", "#DASHDiet #BloodPressure #HeartHealth"),
        ("Fact", "Berberine lowers LDL cholesterol by up to 20% and reduces arterial inflammation.\nIt's been called 'nature's metformin'.", "#Berberine #CholesterolNatural #HeartHealth"),
        ("Warning", "Chronic anger and hostility increase heart attack risk by 2â€“3x.\nAnger management is a serious cardiovascular health intervention.", "#AngerAndHeart #StressAndHealth #HeartHealth"),
    ],
    "male": [
        ("Fact", "Testosterone levels peak at age 18â€“20 and decline 1â€“2% every year after 30.\nBy 50, most men have 30â€“40% less testosterone than their peak.", "#Testosterone #MensHealth #MaleHealth"),
        ("Did You Know?", "Zinc is the most critical mineral for testosterone production.\nJust one oyster contains your entire daily zinc requirement.", "#Zinc #TestosteroneBoost #MensHealth"),
        ("Tip", "Heavy compound lifts (squats, deadlifts, bench press) trigger the highest testosterone release.\n3 sessions per week increases T levels by 20%.", "#TestosteroneExercise #StrengthTraining #MensHealth"),
        ("Warning", "Watching pornography desensitizes dopamine receptors and reduces real-life libido.\nDopamine health is the foundation of male drive.", "#LibidoHealth #MensHealth #DopamineHealth"),
        ("Statistic", "1 in 4 men over 40 have clinically low testosterone.\nLow T causes fatigue, depression, weight gain, and loss of muscle.", "#LowTestosterone #MensHealth #HormoneHealth"),
        ("Fact", "Ashwagandha (KSM-66 extract) raises testosterone by 17% and reduces cortisol by 27% in clinical trials.\nStress reduction = hormone optimization.", "#Ashwagandha #TestosteroneBoost #AdaptogenHerb"),
        ("Did You Know?", "Estrogen dominance in men is now epidemic due to plastics, pesticides, and processed foods.\nXenoestrogens suppress testosterone silently.", "#Estrogen #TestosteroneHealth #MensHealth"),
        ("Tip", "Cold therapy (cold showers, ice baths) raises testosterone and reduces inflammatory cortisol.\nYour testicular temperature directly affects hormone production.", "#ColdTherapy #TestosteroneNatural #MensHealth"),
        ("Warning", "Alcohol consumption reduces testosterone by up to 23% per session.\nEven moderate drinking affects hormone levels for 24 hours.", "#AlcoholAndTestosterone #MensHealth #HormoneBalance"),
        ("Fact", "L-Citrulline is converted to L-Arginine in the kidneys, boosting nitric oxide production more effectively than arginine supplements alone.", "#LCitrulline #NitricOxide #MalePerformance"),
        ("Statistic", "40% of men over 40 have some degree of erectile dysfunction.\nCardiovascular health and ED share the same root causes.", "#MensHealth #CardiovascularHealth #MaleHealth"),
        ("Did You Know?", "Your morning erection is a health indicator.\nMorning wood is caused by nocturnal testosterone surges â€” its absence may signal low T or vascular issues.", "#MensHealth #HormoneHealth #MaleVitality"),
        ("Tip", "Intermittent fasting increases testosterone by 180% in one 24-hour fast.\nFood timing powerfully affects male hormones.", "#IntermittentFasting #TestosteroneBoost #MensHealth"),
        ("Warning", "Soy contains phytoestrogens that can suppress testosterone in high amounts.\nLimit processed soy products (soy milk, tofu daily).", "#SoyAndTestosterone #MensHealth #HormoneHealth"),
        ("Fact", "Icariin (from horny goat weed) is a natural PDE5 inhibitor â€” the same mechanism as Viagra.\nDosing and bioavailability matter significantly.", "#Icariin #NaturalPDE5 #MaleHealth"),
        ("Statistic", "Men with high vitamin D levels have 25% higher testosterone than deficient men.\nSunlight is literally a testosterone booster.", "#VitaminDTestosterone #MensHealth #HormoneHealth"),
        ("Did You Know?", "Tongkat Ali (Eurycoma longifolia) reduces SHBG â€” a protein that binds testosterone and makes it unavailable.\nFree testosterone is what matters.", "#TongkatAli #FreeTestosterone #MensHealth"),
        ("Tip", "7â€“9 hours of sleep is when your body produces 70% of its daily testosterone.\nSleep debt = testosterone debt.", "#SleepAndTestosterone #MensHealth #HormoneOptimization"),
        ("Fact", "Fenugreek extract increases both free and total testosterone by blocking conversion to estrogen.\nIt's also effective for libido and strength.", "#Fenugreek #TestosteroneBoost #MensHealth"),
        ("Warning", "Stress is the #1 testosterone killer in modern men.\nCortisol and testosterone are inversely related â€” one rises, the other falls.", "#StressAndTestosterone #MensHealth #HormoneBalance"),
    ],
    "blood": [
        ("Fact", "Over 100 million Americans have diabetes or prediabetes.\n90% of prediabetics don't know they have it.", "#BloodSugar #Diabetes #PreDiabetes"),
        ("Did You Know?", "A single night of poor sleep makes your cells 25% less responsive to insulin.\nSleep deprivation is a diabetes risk factor.", "#SleepAndBloodSugar #InsulinResistance #BloodSugar"),
        ("Tip", "Apple cider vinegar before meals reduces post-meal blood sugar spikes by 20%.\nThe acetic acid slows carbohydrate digestion.", "#AppleCiderVinegar #BloodSugar #DiabetesPrevention"),
        ("Warning", "White bread and white rice spike blood sugar as fast as pure table sugar.\nChoose whole grain alternatives to flatten glucose curves.", "#GlycemicIndex #BloodSugar #NutritionFacts"),
        ("Statistic", "Reversing prediabetes is possible in 70% of cases through diet and exercise alone.\nMedication is not inevitable.", "#PreDiabetesReversal #BloodSugar #DiabetesPrevention"),
        ("Fact", "Berberine activates AMPK â€” an enzyme that acts like a 'metabolic switch' â€” lowering blood sugar as effectively as metformin in some studies.", "#Berberine #BloodSugar #NaturalDiabetes"),
        ("Did You Know?", "Muscle tissue is your body's largest glucose storage depot.\nBuilding muscle is the most powerful long-term blood sugar management tool.", "#MuscleAndBloodSugar #GlucoseControl #InsulinResistance"),
        ("Tip", "Cinnamon (Ceylon, not Cassia) reduces fasting blood glucose by 11â€“29% in studies.\n1/2 tsp daily is the effective dose.", "#Cinnamon #BloodSugarControl #NaturalRemedies"),
        ("Warning", "Fruit juice removes fiber and concentrates sugar â€” a glass of OJ has the same sugar as 4 oranges.\nEat the whole fruit.", "#FruitJuice #HiddenSugar #BloodSugar"),
        ("Fact", "Chromium picolinate improves insulin sensitivity and reduces sugar cravings.\nDeficiency is extremely common in Western diets.", "#Chromium #InsulinSensitivity #BloodSugar"),
        ("Statistic", "A 7% reduction in body weight reduces diabetes risk by 58% in high-risk individuals.\nYou don't need to lose much to transform your metabolic health.", "#WeightLossDiabetes #BloodSugar #DiabetesPrevention"),
        ("Did You Know?", "Stress causes the liver to dump glucose into the bloodstream, even without eating.\nEmotional stress directly raises blood sugar.", "#StressBloodSugar #CortisolSugar #BloodSugar"),
        ("Tip", "A 10-minute walk immediately after eating is one of the most effective ways to lower post-meal blood sugar.\nYour muscles consume the glucose.", "#PostMealWalk #BloodSugarControl #DiabetesTips"),
        ("Warning", "Many 'low-fat' foods replace fat with added sugar.\nAlways check the sugar content, not just the fat content, on food labels.", "#HiddenSugar #FoodLabels #BloodSugar"),
        ("Fact", "Magnesium is a cofactor in over 300 enzymatic reactions â€” including every step of insulin signaling.\nDeficiency = insulin resistance.", "#MagnesiumInsulin #BloodSugar #DiabetesNutrition"),
        ("Statistic", "People who eat 5+ servings of vegetables daily have a 23% lower risk of type 2 diabetes.\nFiber from vegetables slows glucose absorption.", "#VegetablesAndBloodSugar #DiabetesPrevention #PlantBased"),
        ("Did You Know?", "Your gut bacteria regulate how you metabolize carbohydrates.\nThe same food causes different blood sugar responses in different people based on microbiome composition.", "#GutMicrobiomeBloodSugar #PersonalizedNutrition #BloodSugar"),
        ("Tip", "Resistant starch (cooked-then-cooled rice or potatoes) feeds beneficial bacteria and reduces blood sugar impact by 30%.\nMeal prep carbs strategically.", "#ResistantStarch #BloodSugar #GutHealth"),
        ("Fact", "Alpha-lipoic acid reduces fasting blood sugar, improves insulin sensitivity, and protects nerves damaged by high glucose.\nIt's both water and fat soluble.", "#AlphaLipoicAcid #BloodSugar #DiabetesNeuropathy"),
        ("Warning", "Diet sodas alter gut bacteria in ways that impair glucose metabolism.\nArtificial sweeteners are not neutral for diabetic risk.", "#DietSoda #BloodSugar #ArtificialSweeteners"),
    ],
    "joint": [
        ("Fact", "Cartilage has no blood supply â€” it gets nutrients from the fluid pushed through it during movement.\nSitting still literally starves your joints.", "#JointHealth #Cartilage #JointPain"),
        ("Did You Know?", "Your knees absorb forces of 3â€“5x your body weight with every step.\nLosing 10 lbs reduces knee stress by 40â€“80 lbs per step.", "#KneeHealth #JointPain #WeightAndJoints"),
        ("Tip", "Collagen type II supplementation reduces joint pain by 40% in 6 months.\nIt's the main structural protein in cartilage.", "#CollagenTypeII #JointSupplements #JointHealth"),
        ("Warning", "NSAIDs (ibuprofen, naproxen) mask pain but accelerate cartilage breakdown with long-term use.\nManage inflammation, don't just suppress it.", "#NSAIDs #JointHealth #AntiInflammatory"),
        ("Statistic", "350 million people worldwide live with arthritis.\nInflammatory diet is the most modifiable risk factor.", "#Arthritis #JointHealth #JointPain"),
        ("Fact", "Turmeric's curcumin is as effective as 800mg ibuprofen for osteoarthritis pain in studies.\nCombine with black pepper (piperine) for 2000% better absorption.", "#TurmericJoint #Curcumin #NaturalAntiInflammatory"),
        ("Did You Know?", "Your joints contain synovial fluid â€” nature's lubricant.\nDehydration reduces synovial fluid and causes joint friction and pain.", "#JointLubrication #HydrationAndJoints #JointHealth"),
        ("Tip", "Swimming is the best exercise for joint pain â€” water reduces body weight impact by 90%.\nStrength without stress on the joints.", "#SwimmingBenefits #JointFriendlyExercise #JointPain"),
        ("Warning", "High-sugar diets trigger advanced glycation end products (AGEs) that damage cartilage.\nSugar ages your joints from the inside.", "#SugarAndJoints #Inflammation #JointHealth"),
        ("Fact", "Boswellic acids (from Boswellia) block 5-LOX enzyme â€” the specific enzyme that causes joint inflammation â€” without the side effects of NSAIDs.", "#Boswellia #JointHealth #NaturalAntiInflammatory"),
        ("Statistic", "People who do 150 minutes of moderate exercise per week have 46% lower rates of arthritis progression.\nMovement is medicine for joints.", "#ExerciseAndJoints #Arthritis #JointHealth"),
        ("Did You Know?", "Cold weather doesn't damage joints â€” but it does make the tissue around them stiffen.\nWarm up longer in winter before activity.", "#JointHealth #ColdAndJoints #WinterExercise"),
        ("Tip", "Glucosamine sulfate and chondroitin together reduce joint pain as effectively as celecoxib (Celebrex) for moderate-to-severe osteoarthritis.\nStudy: NEJM 2006.", "#Glucosamine #Chondroitin #JointSupplements"),
        ("Warning", "High-impact running on hard surfaces increases knee joint degeneration risk.\nAlternate with swimming, cycling, or grass running.", "#RunningKnees #JointProtection #ExerciseTips"),
        ("Fact", "Omega-3s reduce systemic inflammation â€” the root driver of arthritis pain.\nFish oil at 2â€“3g EPA/DHA per day shows measurable joint benefits.", "#Omega3Joints #FishOil #JointHealth"),
        ("Statistic", "People who sleep poorly report 2x higher pain sensitivity.\nPoor sleep amplifies joint pain perception in the brain.", "#SleepAndPain #JointHealth #ChronicPain"),
        ("Did You Know?", "Your gut microbiome is directly linked to rheumatoid arthritis.\nCertain bacteria trigger the immune response that attacks joint tissue.", "#GutAndJoints #RheumatoidArthritis #Microbiome"),
        ("Tip", "Anti-inflammatory foods: fatty fish, walnuts, olive oil, berries, dark leafy greens.\nThink 'Mediterranean' for your joints.", "#AntiInflammatoryDiet #JointHealth #MediterraneanDiet"),
        ("Fact", "Vitamin K2 directs calcium into bones and away from joints and arteries.\nK2 deficiency causes calcification of soft tissue â€” including around joints.", "#VitaminK2 #BoneHealth #JointProtection"),
        ("Warning", "Stress causes cortisol spikes that directly increase joint inflammation.\nChronicstress and joint pain create a vicious cycle.", "#StressAndInflammation #JointHealth #ChronicPain"),
    ],
    "sleep": [
        ("Fact", "Chronic sleep deprivation is more dangerous than you think â€” it's been classified as a public health epidemic by the CDC.", "#SleepHealth #SleepScience #BetterSleep"),
        ("Did You Know?", "Your body temperature must drop 1â€“2Â°F to fall asleep.\nA cool bedroom (65â€“68Â°F / 18â€“20Â°C) is not optional â€” it's biological.", "#SleepTemperature #SleepTips #BetterSleep"),
        ("Tip", "Blue light from screens suppresses melatonin by up to 50%.\nStop screen use 90 minutes before bed or use blue-light-blocking glasses.", "#BlueLight #MelatoninNatural #SleepTips"),
        ("Warning", "Alcohol ruins sleep quality even when it helps you fall asleep.\nIt suppresses REM sleep â€” the most restorative stage.", "#AlcoholAndSleep #SleepQuality #SleepFacts"),
        ("Statistic", "People who sleep 7â€“9 hours live significantly longer than those who sleep less than 6.\nSleep is not optional for longevity.", "#SleepAndLongevity #SleepHealth #HealthFacts"),
        ("Fact", "Magnesium glycinate relaxes the nervous system and increases GABA â€” your brain's 'off switch'.\nIt's the most bioavailable form for sleep support.", "#MagnesiumSleep #GABA #NaturalSleepAid"),
        ("Did You Know?", "During deep sleep, your brain cerebrospinal fluid surges to flush out toxic waste â€” including amyloid plaques linked to Alzheimer's.\nSleep literally detoxes your brain.", "#SleepDetox #GlymphaticSystem #BrainHealth"),
        ("Tip", "A consistent wake time is more important than a consistent bedtime.\nYour circadian rhythm anchors on your wake time, not sleep time.", "#SleepSchedule #CircadianRhythm #SleepTips"),
        ("Warning", "Naps longer than 30 minutes cause 'sleep inertia' and disrupt nighttime sleep.\nLimit naps to 20â€“25 minutes before 3pm.", "#NapTips #SleepHealth #PowerNap"),
        ("Fact", "Ashwagandha reduces cortisol by 27% and improves sleep quality scores by 72% in clinical trials.\nAdaptogens work on the stress-sleep axis.", "#Ashwagandha #SleepSupplements #NaturalSleepAid"),
        ("Statistic", "Insomnia increases depression risk by 10x and anxiety risk by 17x.\nSleep disorders are often the root cause of mental health issues.", "#Insomnia #SleepAndMentalHealth #SleepHealth"),
        ("Did You Know?", "Your mattress should be replaced every 7â€“10 years.\nA poor mattress contributes to both back pain and poor sleep quality.", "#MattressTips #SleepHealth #SleepEnvironment"),
        ("Tip", "L-theanine (from green tea) promotes relaxation without sedation.\nIt increases alpha brain waves â€” the same state as meditation.", "#LTheanine #SleepSupplements #RelaxationTips"),
        ("Warning", "Caffeine has a 5â€“7 hour half-life.\nA 3pm coffee still has 50% of its caffeine in your system at 9pm.", "#CaffeineAndSleep #SleepTips #CoffeeTiming"),
        ("Fact", "Valerian root increases GABA in the brain, reducing the time to fall asleep by an average of 15 minutes.\nUse consistently for 2â€“4 weeks for best results.", "#ValerianRoot #NaturalSleepAid #SleepSupplements"),
        ("Statistic", "People with sleep apnea are 3x more likely to have a car accident.\n80% of sleep apnea cases go undiagnosed.", "#SleepApnea #SleepHealth #SleepDisorders"),
        ("Did You Know?", "Sleeping on your left side improves lymphatic drainage and reduces acid reflux.\nSide sleeping also reduces snoring and sleep apnea severity.", "#SleepPosition #LeftSideSleeping #SleepTips"),
        ("Tip", "5-HTP (from Griffonia simplicifolia) converts directly to serotonin, which converts to melatonin.\nAddressing the full sleep-hormone chain works better than melatonin alone.", "#5HTP #Serotonin #NaturalSleepAid"),
        ("Fact", "Exercise improves sleep quality by 65% â€” but timing matters.\nExercise 3+ hours before bed; morning or afternoon is ideal.", "#ExerciseAndSleep #SleepQuality #SleepTips"),
        ("Warning", "Melatonin supplements are 80% unregulated â€” many contain 400% more than labeled.\nDose matters: 0.3â€“1mg is effective; high doses disrupt natural production.", "#MelatoninFacts #SleepSupplements #SleepHealth"),
    ],
    "womens": [
        ("Fact", "70% of bladder leakage cases in women are caused by weakened pelvic floor muscles â€” and 85% respond to targeted exercises.", "#PelvicFloor #WomensHealth #BladderHealth"),
        ("Did You Know?", "Estrogen decline after 40 affects the bladder lining and urethra directly.\nHormonal changes in menopause cause 40% of urinary symptoms.", "#Menopause #WomensHealth #BladderHealth"),
        ("Tip", "Kegel exercises done correctly can reduce urinary leakage by up to 70%.\nTighten, hold for 5 seconds, release â€” 3 sets of 10 daily.", "#KegelExercises #PelvicFloor #WomensHealth"),
        ("Warning", "Caffeine and alcohol irritate the bladder directly.\nReducing coffee to 1 cup per day improves urgency symptoms in 60% of women.", "#BladderHealth #WomensHealth #OveractiveBladder"),
        ("Statistic", "1 in 3 women over 45 experience some form of urinary incontinence.\nIt's extremely common but not inevitable.", "#UrinaryIncontinence #WomensHealth #PelvicHealth"),
        ("Fact", "D-Mannose is a naturally occurring sugar that prevents UTI-causing bacteria from adhering to the bladder wall.\nIt's as effective as antibiotics for uncomplicated UTIs in some studies.", "#DMannose #UTIPrevention #WomensHealth"),
        ("Did You Know?", "Your hormonal cycle affects your entire body â€” not just reproduction.\nEstrogen and progesterone influence brain chemistry, bone density, cardiovascular health, and immune function.", "#HormonalHealth #WomensHealth #HormoneBalance"),
        ("Tip", "Pumpkin seed extract reduces overactive bladder symptoms by 40%.\nClinically studied for both frequency and urgency.", "#PumpkinSeed #BladderHealth #WomensHealth"),
        ("Warning", "High-impact exercise (running, jumping) worsens stress incontinence without pelvic floor strengthening.\nAlways strengthen the pelvic floor before high-impact training.", "#PelvicFloor #ExerciseAndBladder #WomensHealth"),
        ("Fact", "Vitamin D deficiency is linked to overactive bladder and pelvic floor weakness.\nOptimal D3 levels support the smooth muscle tissue of the bladder.", "#VitaminDWomens #BladderHealth #WomensHealth"),
        ("Statistic", "Women experience anxiety and depression at 2x the rate of men.\nHormonal fluctuations directly affect serotonin and GABA neurotransmission.", "#WomensMentalHealth #Hormones #WomensHealth"),
        ("Did You Know?", "Cranberry proanthocyanidins (PACs) are the active compounds that prevent UTIs.\nJuice has too little â€” look for supplements with 36mg PAC daily.", "#Cranberry #UTIPrevention #WomensHealth"),
        ("Tip", "Magnesium glycinate reduces PMS symptoms â€” cramps, mood swings, and water retention â€” better than NSAIDs in some studies.", "#MagnesiumPMS #WomensHealth #PMS"),
        ("Warning", "Synthetic fragrance in feminine hygiene products disrupts vaginal pH and microbiome balance.\nChoose fragrance-free, pH-balanced products.", "#VaginalHealth #WomensHealth #FeminineHygiene"),
        ("Fact", "Probiotics containing Lactobacillus strains protect vaginal microbiome health and reduce recurrent UTIs by 50%.", "#Probiotics #WomensHealth #UTIPrevention"),
        ("Statistic", "1 in 2 women over 50 will experience a bone fracture due to osteoporosis.\nThe window to build bone density closes in your 30s.", "#Osteoporosis #BoneHealth #WomensHealth"),
        ("Did You Know?", "The pelvic floor contains 3 layers of muscles supporting the uterus, bladder, and rectum.\nPregnancy, childbirth, and menopause all weaken these critical muscles.", "#PelvicFloorAnatomy #WomensHealth #PelvicHealth"),
        ("Tip", "Reducing sodium to under 1500mg/day significantly reduces water retention and bloating related to hormonal shifts.", "#SodiumAndBloating #WomensHealth #HormonalHealth"),
        ("Fact", "Saffron extract is as effective as low-dose Prozac for mild-to-moderate depression in women, without the sexual side effects.", "#Saffron #WomensMentalHealth #NaturalAntidepressant"),
        ("Warning", "Hormonal birth control depletes B vitamins, zinc, magnesium, and CoQ10.\nIf you're on the pill, supplement these nutrients actively.", "#BirthControlNutrition #WomensHealth #HormonalHealth"),
    ],
    "general": [
        ("Fact", "The gut contains 70% of the immune system.\nWhat you eat directly determines how well your body fights infection and disease.", "#GutHealth #ImmuneSystem #GeneralHealth"),
        ("Did You Know?", "Your body has 37 trillion cells â€” and every single one is replaced within 7â€“15 years.\nYou are literally building yourself with what you eat.", "#CellRenewal #HealthFacts #GeneralHealth"),
        ("Tip", "Walking 7,000â€“10,000 steps per day reduces all-cause mortality by 53%.\nYou don't need a gym to be healthy.", "#WalkingBenefits #DailySteps #GeneralHealth"),
        ("Warning", "Chronic inflammation is the underlying driver of virtually every major disease â€” cancer, heart disease, diabetes, Alzheimer's.\nYour lifestyle either inflames or protects.", "#ChronicInflammation #HealthFacts #AntiInflammatory"),
        ("Statistic", "Only 12% of Americans are considered metabolically healthy.\nMetabolic health = normal blood sugar, cholesterol, blood pressure, waist size, and triglycerides.", "#MetabolicHealth #HealthFacts #GeneralHealth"),
        ("Fact", "Fasting for 16+ hours activates autophagy â€” your body's cellular recycling and repair system.\nIt's one of the most powerful longevity mechanisms we have.", "#Autophagy #IntermittentFasting #Longevity"),
        ("Did You Know?", "Gratitude practice physically changes the brain â€” it increases activity in the prefrontal cortex and reduces the amygdala's fear response.", "#Gratitude #MindsetHealth #MentalHealth"),
        ("Tip", "Sunlight in the morning sets your circadian rhythm, boosts serotonin, and increases vitamin D.\n10â€“15 minutes outside within 1 hour of waking is the single best health habit.", "#MorningSunlight #CircadianRhythm #VitaminD"),
        ("Warning", "Most Americans are deficient in at least one essential nutrient.\nThe most common deficiencies: Vitamin D, magnesium, Omega-3, and zinc.", "#NutrientDeficiency #HealthFacts #Supplementation"),
        ("Fact", "The liver processes over 500 different functions â€” including detoxification, hormone regulation, and cholesterol production.\nLiver health = total body health.", "#LiverHealth #Detoxification #GeneralHealth"),
        ("Statistic", "People with strong social connections live an average of 7 years longer.\nSocial health is as important as diet and exercise.", "#SocialHealth #Longevity #GeneralHealth"),
        ("Did You Know?", "Laughter literally boosts NK cells (Natural Killer cells) that fight cancer and viruses.\nHumor is immune medicine.", "#Laughter #ImmuneBoost #GeneralHealth"),
        ("Tip", "Deep breathing for 5 minutes activates the vagus nerve and switches your nervous system from 'fight-or-flight' to 'rest-and-digest'.\nControl your stress with your breath.", "#DeepBreathing #VagusNerve #StressRelief"),
        ("Warning", "Processed foods contain endocrine disruptors, artificial dyes, and preservatives that disrupt hormone function.\nEat whole foods at least 80% of the time.", "#ProcessedFood #EndocrineDisruptors #GeneralHealth"),
        ("Fact", "Zinc is required for over 300 enzymatic reactions in the human body.\nDeficiency impairs immunity, hormone production, wound healing, and taste/smell.", "#Zinc #NutritionFacts #GeneralHealth"),
        ("Statistic", "People who meditate regularly have telomeres 10% longer than non-meditators.\nLonger telomeres = slower biological aging.", "#Meditation #Telomeres #Longevity"),
        ("Did You Know?", "Your body produces its own antioxidants (glutathione, catalase, SOD).\nThe goal of nutrition is to support this internal production â€” not just take external antioxidants.", "#Glutathione #Antioxidants #GeneralHealth"),
        ("Tip", "Cold + heat contrast therapy (sauna then cold plunge) boosts growth hormone by 200â€“300% and improves cardiovascular resilience.", "#ContrastTherapy #Sauna #Longevity"),
        ("Fact", "Olive oil's oleocanthal has the same anti-inflammatory mechanism as ibuprofen.\n3â€“4 tablespoons of extra virgin olive oil per day provides therapeutic doses.", "#OliveOil #AntiInflammatory #GeneralHealth"),
        ("Warning", "Chronic stress shrinks the hippocampus, suppresses immunity, and accelerates aging at the cellular level.\nStress isn't just in your head â€” it's in every cell.", "#ChronicStress #HealthWarning #GeneralHealth"),
    ],
}

# Photo search queries per board — real people matching the audience demographic
PHOTO_QUERIES = {
    "dental":   "woman beautiful smile healthy teeth whitening",
    "prostate": "active man over 50 healthy outdoor lifestyle",
    "male":     "confident fit man energy gym workout strength",
    "brain":    "woman meditation calm focus mental wellness",
    "weight":   "woman healthy lifestyle fitness active body",
    "beauty":   "woman skincare glow natural radiant skin",
    "womens":   "woman wellness health natural lifestyle 40s",
    "blood":    "healthy colorful vegetables nutrition food",
    "joint":    "woman yoga flexibility active joints wellness",
    "sleep":    "woman sleeping peaceful bedroom rest cozy",
    "heart":    "active woman running cardio outdoor heart health",
    "general":  "healthy family wellness lifestyle outdoors",
}


def fetch_pexels_photo(board_key):
    """Download a portrait photo from Pexels for the given board. Returns PIL Image or None."""
    import requests as _req
    if not PEXELS_API_KEY:
        return None
    query = PHOTO_QUERIES.get(board_key, "health wellness lifestyle")
    try:
        r = _req.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "orientation": "portrait", "size": "large", "per_page": 15},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        photos = r.json().get("photos", [])
        if not photos:
            return None
        photo = random.choice(photos)
        img_url = photo["src"].get("large2x") or photo["src"].get("large")
        ir = _req.get(img_url, timeout=20)
        if ir.status_code != 200:
            return None
        return Image.open(io.BytesIO(ir.content)).convert("RGB")
    except Exception:
        return None


def _crop_cover(img, tw, th):
    """Resize + center-crop to fill tw×th (cover mode)."""
    ow, oh = img.size
    scale = max(tw / ow, th / oh)
    nw, nh = int(ow * scale), int(oh * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top  = (nh - th) // 2
    return img.crop((left, top, left + tw, top + th))


def _gradient_overlay(img):
    """Apply a bottom-heavy dark gradient so white text is readable over any photo."""
    W, H = img.size
    # Subtle all-over tint
    tint = Image.new("RGBA", (W, H), (0, 0, 0, 45))
    result = Image.alpha_composite(img.convert("RGBA"), tint)
    # Stronger gradient in bottom 78%
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(grad)
    start = int(H * 0.22)
    for y in range(start, H):
        t = (y - start) / (H - start)
        a = int(t * t * 212)
        d.rectangle([0, y, W, y + 1], fill=(0, 0, 0, a))
    return Image.alpha_composite(result, grad).convert("RGB")


def make_pin_image(board_key, headline, body, hashtags):
    import textwrap
    W, H = 1000, 1500
    accent    = BOARDS[board_key]["accent"]
    board_name = BOARDS[board_key]["name"]

    # Try Pexels photo — fall back to dark programmatic background
    photo = fetch_pexels_photo(board_key)
    if photo:
        img        = _crop_cover(photo, W, H)
        img        = _gradient_overlay(img)
        head_color = (255, 255, 255)
        body_color = (238, 238, 238)
        use_shadow = True
    else:
        img = Image.new("RGB", (W, H), (14, 14, 18))
        for cx, cy, r, af in [(850, 200, 220, 0.06), (-50, 1350, 280, 0.05), (500, 750, 600, 0.03)]:
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            od.ellipse([cx-r, cy-r, cx+r, cy+r],
                       fill=(accent[0], accent[1], accent[2], int(255 * af)))
            img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        head_color = (255, 255, 255)
        body_color = (200, 200, 210)
        use_shadow = False

    draw = ImageDraw.Draw(img)

    BOLD = [
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    REG = [
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    def ttf(paths, size):
        for p in paths:
            try:    return ImageFont.truetype(p, size)
            except: pass
        return ImageFont.load_default()

    f_badge = ttf(BOLD, 26)
    f_label = ttf(BOLD, 36)
    f_head  = ttf(BOLD, 70)
    f_body  = ttf(REG,  41)
    f_hash  = ttf(REG,  29)
    f_url   = ttf(BOLD, 30)
    f_sub   = ttf(REG,  26)

    def put(d, xy, text, font, color):
        if use_shadow:
            d.text((xy[0]+3, xy[1]+3), text, font=font, fill=(0, 0, 0))
        d.text(xy, text, font=font, fill=color)

    # Board category pill (top-left)
    badge_txt = board_name.upper()
    bb = draw.textbbox((0, 0), badge_txt, font=f_badge)
    bw, bh = bb[2]-bb[0]+36, bb[3]-bb[1]+16
    draw.rounded_rectangle([50, 50, 50+bw, 50+bh], radius=bh//2, fill=accent)
    draw.text((68, 50+8-bb[1]), badge_txt, font=f_badge, fill=(255, 255, 255))

    # Headline type label (e.g. "Did You Know?")
    label_y = 680
    lb = draw.textbbox((0, 0), headline, font=f_label)
    lw, lh = lb[2]-lb[0]+28, lb[3]-lb[1]+14
    draw.rounded_rectangle([50, label_y, 50+lw, label_y+lh], radius=6,
                            fill=(max(0, accent[0]-60), max(0, accent[1]-60), max(0, accent[2]-60)))
    draw.text((64, label_y+7-lb[1]), headline, font=f_label, fill=accent)

    # Divider
    div_y = label_y + lh + 16
    draw.rectangle([50, div_y, 950, div_y+2], fill=(200, 200, 200))

    # Body text
    body_y = div_y + 26
    lines  = []
    for para in body.split("\n"):
        para = para.strip()
        if para:
            lines.extend(textwrap.wrap(para, width=26))
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()

    first_txt = lines[0] if lines else ""
    rest      = lines[1:] if lines else []

    # First line — large & bold
    fbb = draw.textbbox((0, 0), first_txt, font=f_head)
    fx  = max(50, (W-(fbb[2]-fbb[0]))//2)
    put(draw, (fx, body_y-fbb[1]), first_txt, f_head, head_color)

    cur_y = body_y + 94
    for ln in rest:
        if ln == "":
            cur_y += 22; continue
        lbb = draw.textbbox((0, 0), ln, font=f_body)
        lx  = max(50, (W-(lbb[2]-lbb[0]))//2)
        put(draw, (lx, cur_y-lbb[1]), ln, f_body, body_color)
        cur_y += 58

    # Hashtags
    hash_y = max(cur_y+18, 1220)
    hb  = draw.textbbox((0, 0), hashtags, font=f_hash)
    hx  = (W-(hb[2]-hb[0]))//2
    put(draw, (hx, hash_y-hb[1]), hashtags, f_hash, accent)

    # Footer dark bar
    draw.rectangle([0, 1370, W, 1500], fill=(8, 8, 12))
    url_txt = "reviews.thehappy-healthy-life.com"
    ub = draw.textbbox((0, 0), url_txt, font=f_url)
    ux = (W-(ub[2]-ub[0]))//2
    draw.text((ux, 1393-ub[1]), url_txt, font=f_url, fill=(255, 255, 255))
    sub_txt = "Full supplement reviews • Link in bio"
    sb = draw.textbbox((0, 0), sub_txt, font=f_sub)
    sx = (W-(sb[2]-sb[0]))//2
    draw.text((sx, 1440-sb[1]), sub_txt, font=f_sub, fill=(150, 150, 160))
    draw.rectangle([0, 1492, W, 1500], fill=accent)

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def upload_pin(board_id, title, description, img_bytes, link, headers):
    import requests

    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    payload = {
        "title": title[:100],
        "description": description[:500],
        "board_id": board_id,
        "media_source": {
            "source_type": "image_base64",
            "content_type": "image/png",
            "data": img_b64,
        },
        "link": link,
    }
    for attempt in range(3):
        try:
            r = requests.post(
                "https://api.pinterest.com/v5/pins",
                json=payload, headers=headers, timeout=60
            )
            return r.status_code, r.json()
        except Exception as e:
            log(f"  upload_pin erreur tentative {attempt+1}: {e}")
            time.sleep(5)
    return 0, {"error": "echec apres 3 tentatives"}


# â”€â”€ Logging â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def log(msg):
    print(msg, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC] {msg}\n")
    except Exception:
        pass


# â”€â”€ State management â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def load_done():
    if not os.path.exists(DONE_FILE):
        return {}
    try:
        with open(DONE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_done(done):
    with open(DONE_FILE, "w", encoding="utf-8") as f:
        json.dump(done, f, indent=2)

def load_idx():
    try:
        with open(IDX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"board_idx": 0, "content_idx": {}}

def save_idx(state):
    with open(IDX_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ── Video Idea Pin helpers ────────────────────────────────────────────────────

# Pexels search queries per category — real people, health-related
PEXELS_QUERIES = {
    "dental-health":    ["woman smiling healthy teeth", "dental care woman", "oral hygiene"],
    "prostate-health":  ["senior man active healthy", "older man jogging", "men health doctor"],
    "male-performance": ["man workout fitness", "athletic man training", "male energy fitness"],
    "brain-and-senses": ["woman meditation focus", "person studying concentration", "brain health yoga"],
    "weight-loss":      ["woman healthy eating salad", "fitness woman exercise", "weight loss workout"],
    "beauty-skin":      ["woman skincare routine", "healthy glowing skin woman", "beauty face care"],
    "womens-health":    ["woman yoga wellness", "healthy woman exercise", "women fitness lifestyle"],
    "blood-sugar":      ["healthy eating vegetables", "person diabetes care", "woman healthy diet"],
    "joint-pain":       ["senior person stretching", "older adult exercise", "joint mobility workout"],
    "sleep":            ["person sleeping peacefully", "woman resting bed", "good night sleep"],
    "heart-health":     ["woman running cardio", "heart healthy lifestyle", "person exercise health"],
    "general-health":   ["healthy lifestyle woman", "wellness nutrition", "person healthy living"],
}


def load_all_products():
    """Return all active products from products.json."""
    products_file = os.path.join(BASE_DIR, "products.json")
    try:
        with open(products_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    result = []
    for cat in data.get("categories", []):
        for p in cat.get("products", []):
            if p.get("status") == "ok":
                result.append({**p, "category_slug": cat["slug"]})
    return result


def pexels_search_video(query, api_key, orientation="portrait", per_page=10):
    """Search Pexels for a video. Returns a download URL or None."""
    import requests
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": api_key},
            params={"query": query, "orientation": orientation, "per_page": per_page, "size": "medium"},
            timeout=30,
        )
        if r.status_code != 200:
            log(f"    Pexels search failed {r.status_code}")
            return None
        videos = r.json().get("videos", [])
        if not videos:
            return None
        # Pick a random video from results to vary content
        video = random.choice(videos[:5])
        # Prefer HD or SD file
        files = video.get("video_files", [])
        # Sort by quality: prefer 1080p portrait, then any portrait, then any
        files_sorted = sorted(
            files,
            key=lambda f: (
                "hd" in (f.get("quality") or ""),
                f.get("width", 0) <= f.get("height", 1),  # portrait preferred
                f.get("height", 0),
            ),
            reverse=True,
        )
        for f in files_sorted:
            url = f.get("link")
            if url:
                return url
    except Exception as e:
        log(f"    Pexels exception: {e}")
    return None


def download_video(url, dest_path):
    """Download a video from URL to dest_path."""
    import requests
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
    size_kb = os.path.getsize(dest_path) // 1024
    log(f"    Downloaded {size_kb} KB")


def get_video_duration(path):
    """Return video duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 30.0


async def _tts_async(text, path, voice="en-US-AriaNeural"):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice=voice, rate="+5%", volume="+10%")
    await communicate.save(path)


def make_voiceover(product, audio_path):
    name = product["name"]
    desc = product.get("description", "a popular supplement")
    gravity = product.get("gravity", 0)
    rating = min(4.9, max(3.8, 3.5 + gravity / 50))
    script = (
        f"Looking for an honest review of {name}? "
        f"{name} is {desc[:200].rstrip('.')}. "
        f"With thousands of satisfied customers and a rating of {rating:.1f} out of five, "
        f"it's one of the most trusted supplements in its category. "
        f"Read our full review — link in bio. "
        f"Follow for more honest health supplement reviews."
    )
    asyncio.run(_tts_async(script, audio_path))


def get_font_paths():
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def process_video_with_overlay(raw_path, audio_path, output_path, product):
    """
    Crop raw video to 9:16 (1080x1920), add dark bottom overlay + text,
    mix in voiceover audio, clamp duration to min(60s, audio_duration).
    """
    name = product["name"]
    gravity = product.get("gravity", 0)
    rating = min(4.9, max(3.8, 3.5 + gravity / 50))
    stars = "★" * int(round(rating)) + "☆" * (5 - int(round(rating)))

    audio_dur = get_video_duration(audio_path)
    target_dur = min(60.0, audio_dur + 1.5)

    font_path = get_font_paths()
    font_filter = ""
    if font_path:
        safe_font = font_path.replace(":", "\\:")
        # Bottom gradient overlay + 3 text lines
        font_filter = (
            f"drawbox=x=0:y=ih*0.62:w=iw:h=ih*0.38:color=black@0.65:t=fill,"
            f"drawtext=fontfile={safe_font}:text='{name}':fontsize=58:fontcolor=white"
            f":x=(w-text_w)/2:y=h*0.65:shadowx=2:shadowy=2,"
            f"drawtext=fontfile={safe_font}:text='{stars} {rating:.1f}/5':fontsize=44"
            f":fontcolor=gold:x=(w-text_w)/2:y=h*0.75:shadowx=1:shadowy=1,"
            f"drawtext=fontfile={safe_font}:text='thehappy-healthy-life.com':fontsize=34"
            f":fontcolor=white@0.9:x=(w-text_w)/2:y=h*0.84,"
            f"drawtext=fontfile={safe_font}:text='FULL REVIEW IN BIO':fontsize=36"
            f":fontcolor=yellow:x=(w-text_w)/2:y=h*0.91:shadowx=1:shadowy=1"
        )
    else:
        font_filter = "drawbox=x=0:y=ih*0.7:w=iw:h=ih*0.3:color=black@0.7:t=fill"

    # Video filter: scale + crop to portrait 9:16, then overlay text
    vf = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"{font_filter}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",          # loop the stock video if shorter than audio
        "-i", raw_path,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-t", str(target_dur),
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"    FFmpeg error: {result.stderr[-300:]}")
        raise RuntimeError("ffmpeg failed")
    size_kb = os.path.getsize(output_path) // 1024
    log(f"    Video ready: {size_kb} KB, {target_dur:.1f}s")


def load_video_idx():
    try:
        with open(VIDEO_IDX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"idx": 0}


def save_video_idx(state):
    with open(VIDEO_IDX_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def upload_video_to_pinterest(mp4_path, headers):
    """Register upload with Pinterest, push to S3, poll until ready. Returns media_id or None."""
    import requests

    r = requests.post(
        "https://api.pinterest.com/v5/media",
        json={"media_type": "video"},
        headers=headers,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        log(f"    video register failed {r.status_code}: {r.text[:200]}")
        return None

    data = r.json()
    media_id = data.get("media_id")
    upload_url = data.get("upload_url")
    upload_params = data.get("upload_parameters", {})

    if not media_id or not upload_url:
        log(f"    video register missing fields: {list(data.keys())}")
        return None

    file_size = os.path.getsize(mp4_path)
    log(f"    media_id={media_id}, uploading {file_size // 1024}KB to S3...")

    with open(mp4_path, "rb") as fh:
        video_bytes = fh.read()

    form_fields = {k: (None, v) for k, v in upload_params.items()}
    form_fields["file"] = ("video.mp4", video_bytes, "video/mp4")

    s3 = requests.post(upload_url, files=form_fields, timeout=300)
    if s3.status_code not in (200, 201, 204):
        log(f"    S3 upload failed {s3.status_code}")
        return None

    log(f"    S3 ok, polling media status...")
    for _ in range(30):
        time.sleep(10)
        pr = requests.get(
            f"https://api.pinterest.com/v5/media/{media_id}",
            headers=headers,
            timeout=30,
        )
        if pr.status_code == 200:
            status = pr.json().get("status", "")
            log(f"    status={status}")
            if status == "succeeded":
                return media_id
            if status == "failed":
                log(f"    video processing failed")
                return None

    log(f"    video processing timed out after 5 min")
    return None


def publish_video_pin(headers):
    """
    Publish one video Idea Pin with real people from Pexels.
    Pipeline: Pexels search → download → edge-tts voiceover → FFmpeg overlay → Pinterest upload.
    """
    import requests

    if not PEXELS_API_KEY:
        log("  [VIDEO] PEXELS_API_KEY not set — skip")
        return False

    products = load_all_products()
    if not products:
        log("  [VIDEO] No products found — skip")
        return False

    v_state = load_video_idx()
    idx = v_state.get("idx", 0) % len(products)
    product = products[idx]
    v_state["idx"] = idx + 1
    save_video_idx(v_state)

    slug = product["slug"]
    name = product["name"]
    cat_slug = product["category_slug"]

    board_key = CAT_TO_BOARD.get(cat_slug)
    if not board_key or board_key not in BOARDS:
        log(f"  [VIDEO] No board mapped for {cat_slug} — skip")
        return False

    board = BOARDS[board_key]
    link = f"{SITE_URL}/{cat_slug}/{slug}/"
    log(f"  [VIDEO] {name} ({cat_slug}) -> {board['name']}")

    # Search Pexels for a real-person video matching this category
    queries = PEXELS_QUERIES.get(cat_slug, ["healthy lifestyle"])
    video_url = None
    for query in queries:
        log(f"    Pexels search: '{query}'")
        video_url = pexels_search_video(query, PEXELS_API_KEY)
        if video_url:
            break

    if not video_url:
        log("  [VIDEO] No Pexels video found — skip")
        return False

    with tempfile.TemporaryDirectory() as tmp:
        raw_path    = os.path.join(tmp, "raw.mp4")
        audio_path  = os.path.join(tmp, "voice.mp3")
        output_path = os.path.join(tmp, "final.mp4")

        log(f"    Downloading stock video...")
        try:
            download_video(video_url, raw_path)
        except Exception as e:
            log(f"    Download failed: {e}")
            return False

        log(f"    Generating voiceover (edge-tts)...")
        try:
            make_voiceover(product, audio_path)
        except Exception as e:
            log(f"    TTS failed: {e}")
            return False

        log(f"    Processing video with FFmpeg overlay...")
        try:
            process_video_with_overlay(raw_path, audio_path, output_path, product)
        except Exception as e:
            log(f"    FFmpeg failed: {e}")
            return False

        log(f"    Uploading to Pinterest...")
        media_id = upload_video_to_pinterest(output_path, headers)
        if not media_id:
            return False

    gravity = product.get("gravity", 0)
    rating = min(4.9, max(3.8, 3.5 + gravity / 50))
    payload = {
        "title": f"{name} Review {datetime.utcnow().year} — {rating:.1f}/5 ⭐",
        "description": (
            f"Honest review of {name}. {product.get('description', '')[:200]} "
            f"Real results, no fluff. Full review: {link} "
            f"#supplementreview #{cat_slug.replace('-', '')} #healthtips #honestreviews"
        )[:500],
        "board_id": board["id"],
        "media_source": {
            "source_type": "video_id",
            "media_id": media_id,
        },
        "link": link,
    }

    for attempt in range(3):
        try:
            r = requests.post(
                "https://api.pinterest.com/v5/pins",
                json=payload, headers=headers, timeout=60,
            )
            if r.status_code in (200, 201):
                log(f"    VIDEO pin OK pin_id={r.json().get('id', '?')}")
                return True
            log(f"    VIDEO pin erreur {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log(f"    VIDEO pin exception tentative {attempt + 1}: {e}")
            time.sleep(5)
    return False


# â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main():
    if not PINTEREST_TOKEN:
        log("ERREUR: PINTEREST_ACCESS_TOKEN non defini")
        sys.exit(1)

    tz_tunis = timezone(timedelta(hours=1))
    today_key = datetime.now(timezone.utc).astimezone(tz_tunis).strftime("%Y-%m-%d")

    done = load_done()
    if done.get(today_key):
        log(f"Pinterest deja publie pour {today_key}")
        sys.exit(0)

    state = load_idx()
    board_idx = state.get("board_idx", 0)
    content_idx = state.get("content_idx", {})

    headers = {
        "Authorization": f"Bearer {PINTEREST_TOKEN}",
        "Content-Type": "application/json",
    }

    log(f"=== Pinterest Educational Publisher {today_key} ({PINS_PER_DAY} pins) ===")

    published = 0
    errors = 0

    for i in range(PINS_PER_DAY):
        board_key = BOARD_ROTATION[board_idx % len(BOARD_ROTATION)]
        board = BOARDS[board_key]
        board_idx += 1

        items = CONTENT[board_key]
        cidx = content_idx.get(board_key, 0) % len(items)
        content_idx[board_key] = cidx + 1

        headline, body, hashtags = items[cidx]

        # Build pin metadata
        cat_url = board["cat_url"]
        link = f"{SITE_URL}/{cat_url}/"
        first_line = body.split("\n")[0].strip()
        title = f"{headline}: {first_line}"[:100]
        description = f"{body.replace(chr(10), ' ')} | Full reviews: {link}"[:500]

        log(f"  [{i+1}/{PINS_PER_DAY}] {board['name']} â€” {headline}: {first_line[:50]}")

        # Generate image
        try:
            img_bytes = make_pin_image(board_key, headline, body, hashtags)
        except Exception as e:
            log(f"    Image generation failed: {e}")
            errors += 1
            continue

        # Upload pin
        status, resp = upload_pin(board["id"], title, description, img_bytes, link, headers)
        if status in (200, 201):
            pin_id = resp.get("id", "?")
            log(f"    OK pin_id={pin_id}")
            published += 1
        else:
            log(f"    ERREUR {status}: {resp}")
            errors += 1

        if i < PINS_PER_DAY - 1:
            time.sleep(5)

    state["board_idx"] = board_idx
    state["content_idx"] = content_idx
    save_idx(state)

    log("=== Video Idea Pin ===")
    publish_video_pin(headers)

    done[today_key] = {
        "published": published,
        "errors": errors,
        "at": datetime.utcnow().isoformat(),
    }
    save_done(done)
    log(f"=== Termine: {published} publies | {errors} erreurs ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log(f"EXCEPTION:\n{traceback.format_exc()}")
        sys.exit(1)
