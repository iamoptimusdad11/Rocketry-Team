// STAR FIELD

const canvas =
document.getElementById("stars");

const ctx =
canvas.getContext("2d");


canvas.width =
window.innerWidth;

canvas.height =
window.innerHeight;



let stars=[];


for(let i=0;i<250;i++){

stars.push({

x:Math.random()*canvas.width,

y:Math.random()*canvas.height,

size:Math.random()*2

});

}



function drawStars(){


ctx.clearRect(
0,
0,
canvas.width,
canvas.height
);


ctx.fillStyle="white";


stars.forEach(star=>{


ctx.beginPath();

ctx.arc(
star.x,
star.y,
star.size,
0,
Math.PI*2
);

ctx.fill();


star.y += .3;


if(star.y > canvas.height){

star.y=0;

}


});


requestAnimationFrame(drawStars);

}


drawStars();






// TELEMETRY SIMULATION


let altitude=0;

let velocity=0;

let temperature=20;



setInterval(()=>{


altitude += Math.floor(Math.random()*80);

velocity += Math.floor(Math.random()*10);

temperature += (Math.random()-.5).toFixed(1);



document.getElementById("altitude")
.innerHTML =
altitude.toLocaleString();



document.getElementById("velocity")
.innerHTML =
velocity.toLocaleString();



document.getElementById("temperature")
.innerHTML =
temperature;



},1000);