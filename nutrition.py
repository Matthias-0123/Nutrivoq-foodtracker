
import math


ACTIVITY_LEVELS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9
}

GOAL_ADJUSTMENTS = {
    "gain": 300,
    "maintain": 0,
    "lose": -400
}


def calculate_calorie_goal(
    weight,
    height,
    age,
    sex,
    activity_level,
    goal="maintain"
):
    weight = float(weight)
    height = float(height)
    age = int(age)

    if not all(math.isfinite(value) for value in (weight, height)):
        raise ValueError("Invalid body measurements.")

    if weight <= 0 or height <= 0 or age <= 0:
        raise ValueError("Body measurements must be positive.")

    if sex == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    elif sex == "female":
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    else:
        raise ValueError("Invalid sex.")

    if isinstance(activity_level, str):
        if activity_level in ACTIVITY_LEVELS:
            activity_multiplier = ACTIVITY_LEVELS[activity_level]
        else:
            activity_multiplier = float(activity_level)
    else:
        activity_multiplier = float(activity_level)

    if not math.isfinite(activity_multiplier):
        raise ValueError("Invalid activity level.")

    if activity_multiplier not in ACTIVITY_LEVELS.values():
        raise ValueError("Invalid activity level.")

    if goal not in GOAL_ADJUSTMENTS:
        raise ValueError("Invalid fitness goal.")

    maintenance_calories = bmr * activity_multiplier

    calorie_goal = (
        maintenance_calories + GOAL_ADJUSTMENTS[goal]
    )

    return round(max(1200, calorie_goal))


def calculate_macros(calorie_goal, weight, goal="maintain"):
    calorie_goal = int(calorie_goal)
    weight = float(weight)

    if calorie_goal <= 0 or not math.isfinite(weight) or weight <= 0:
        raise ValueError("Invalid calorie goal or weight.")

    protein_multipliers = {
        "gain": 1.8,
        "maintain": 1.6,
        "lose": 2.0
    }

    if goal not in protein_multipliers:
        raise ValueError("Invalid fitness goal.")

    protein = round(
        weight * protein_multipliers[goal]
    )

    fat = round(weight * 0.9)

    remaining_calories = calorie_goal - (
        protein * 4 + fat * 9
    )

    carbs = round(max(0, remaining_calories) / 4)

    return {
        "calories": calorie_goal,
        "protein": protein,
        "carbs": carbs,
        "fat": fat
    }
