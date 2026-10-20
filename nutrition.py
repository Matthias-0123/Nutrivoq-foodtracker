
def calculate_calorie_goal(weight, height, age, sex, activity_level):
    if sex == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    maintenance_calories = bmr * activity_level
    return round(maintenance_calories + 300)


def calculate_macros(calorie_goal, weight):
    protein = round(weight * 1.8)
    fat = round(weight * 0.9)

    remaining_calories = calorie_goal - (protein * 4 + fat * 9)
    carbs = round(max(0, remaining_calories) / 4)

    return {
        "calories": calorie_goal,
        "protein": protein,
        "carbs": carbs,
        "fat": fat
    }
