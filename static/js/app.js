
// --------------------------------------------------
// AUX WARS CLIENT LOGIC
// --------------------------------------------------

// Connect to Flask Socket.IO server
const socket = io();

// --------------------------------------------------
// Animate hero content on page load
// --------------------------------------------------
gsap.from(".hero-left", {
    opacity: 0,
    y: 40,
    duration: 1
});

gsap.from(".battle-card", {
    opacity: 0,
    scale: 0.92,
    duration: 1.1
});

// --------------------------------------------------
// Simulated voting action
// --------------------------------------------------
function vote() {
    socket.emit("send_vote", {
        side: "left"
    });
}

// --------------------------------------------------
// Receive live vote updates
// --------------------------------------------------
socket.on("vote_update", (data) => {

    // Total votes
    const total = data.left + data.right;

    // Calculate percentages
    const leftPercent = (data.left / total) * 100;
    const rightPercent = (data.right / total) * 100;

    // Update vote bars
    document.getElementById("leftVotes").style.width = leftPercent + "%";
    document.getElementById("rightVotes").style.width = rightPercent + "%";
});

// --------------------------------------------------
// Trigger cinematic winner reveal
// --------------------------------------------------
function finishBattle() {
    socket.emit("battle_finish");
}

// --------------------------------------------------
// Winner reveal animation
// --------------------------------------------------
socket.on("winner_reveal", (data) => {

    const popup = document.getElementById("winnerPopup");

    document.getElementById("winnerText").innerText =
        data.winner + " WINS";

    document.getElementById("eloText").innerText =
        "+" + data.elo_gain + " ELO";

    popup.style.display = "block";

    gsap.fromTo(
        popup,
        {
            scale: 0.7,
            opacity: 0
        },
        {
            scale: 1,
            opacity: 1,
            duration: 0.8,
            ease: "back.out(1.7)"
        }
    );
});

// --------------------------------------------------
// Floating card tilt effect
// --------------------------------------------------
document.querySelectorAll(".leaderboard-card").forEach((card) => {

    card.addEventListener("mousemove", (e) => {

        const rect = card.getBoundingClientRect();

        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const rotateY = ((x / rect.width) - 0.5) * 12;
        const rotateX = ((y / rect.height) - 0.5) * -12;

        card.style.transform =
            `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
    });

    card.addEventListener("mouseleave", () => {
        card.style.transform = "rotateX(0) rotateY(0)";
    });
});
