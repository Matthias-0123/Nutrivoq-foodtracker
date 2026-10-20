
from flask import Flask, render_template, request

app = Flask(__name__)


def calculate_calorie_goal(weight, height, age, sex, activity_level):
    if sex == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    maintenance_calories = bmr * activity_level
    calorie_goal = round(maintenance_calories + 300)

    return calorie_goal


def calculate_macros(calorie_goal, weight):
    protein = round(weight * 1.8)
    fat = round(weight * 0.9)

    remaining_calories = calorie_goal - (protein * 4 + fat * 9)
    carbs = round(max(0, remaining_calories) / 4)

    return {
        "calories": calorie_goal,
        "protein": protein,
        "fat": fat,
        "carbs": carbs
    }


@app.route("/", methods=["GET", "POST"])
def index():
    goals = None

    if request.method == "POST":
        weight = float(request.form["weight"])
        height = float(request.form["height"])
        age = int(request.form["age"])
        sex = request.form["sex"]
        activity_level = float(request.form["activity_level"])

        calorie_goal = calculate_calorie_goal(
            weight, height, age, sex, activity_level
        )

        goals = calculate_macros(calorie_goal, weight)

    return render_template("index.html", goals=goals)


if __name__ == "__main__":
    app.run(debug=True)
