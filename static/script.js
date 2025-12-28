function calculateLoan() {
    let amount = document.getElementById('amount').value;
    let rate = document.getElementById('rate').value;
    let months = document.getElementById('months').value;

    if(amount == "" || rate == "" || months == "") {
        alert("Please fill in all fields");
        return;
    }

    let interest = (amount * (rate * 0.01)) / months;
    let total = ((amount / months) + interest).toFixed(2);

    document.getElementById('monthly-payment').innerText = "Monthly Payment: $" + total;
}