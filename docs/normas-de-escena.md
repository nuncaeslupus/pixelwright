# Normas de escena

Aprendidas con escenas de prueba (la cripta y la plaça de Sant Felip Neri), hechas para mejorar las herramientas de pixelwright. Se amplían con cada ronda de revisión.

## Cámara y escala
1. Todas las escenas usan la misma cámara: ojos a 1,6 m y vista frontal. La línea del horizonte pasa por los ojos de todos los personajes de pie.
2. La altura de una persona en píxeles es ≈ 1,09 × (y de los pies − y del horizonte), porque 1,75 m / 1,6 m ≈ 1,09. Cada escena guarda en `[scene.scale]` una referencia (`person` o `door`, con su `y` y su `height` en píxeles) elegida para que cumpla esa relación, es decir, para que la cámara quede a 1,6 m.
3. El tamaño "normal" del personaje es el de la cripta (la escena más cercana). Los planos lejanos usan 2 o 3 versiones dibujadas a mano; no se escala a factores no enteros.
4. No forzar la perspectiva para que quepa algo: si un objeto no cabe en el encuadre, se quita.
5. Abrir el encuadre lo justo para que se lean los límites del espacio (en la plaza, la pared izquierda en ángulo), aceptando personajes algo más pequeños.

## Composición
6. Escenas de 640 px de ancho = dos pantallas de 320. El corte no cae en una junta entre edificios; algo debe asomar en la primera pantalla para invitar a ir a la derecha.
7. Los elementos principales (fuente, portal) van centrados y simétricos, con una cara plana hacia la cámara.
8. El primer plano lleva algo habitable (terraza de bar, mesas juntas): sitios para personajes sentados.
9. Los objetos se apoyan siguiendo la orientación de su pared (bici en el túnel paralela al muro) y no tapan entradas ni pasos.
10. Los pasos (arcos, túneles) no se ven de punta a punta: el túnel gira y solo asoma la mitad de la salida. Así se entiende que sigue una pared.
11. Árboles: copas que no tapen los focos (la hornacina). Se pueden simplificar respecto a la realidad.

## Luz
12. La dirección del sol sale del mapa real. Las sombras se calculan desde el sol (dirección y altura), no se colocan a ojo.
13. Cada pared tiene su tono según mire al sol; la pared más orientada al sol es la más clara.
14. Los objetos conservan su propia luz encima de las sombras proyectadas: cara al sol clara, cara opuesta oscura.
15. En un interior visto desde fuera (un túnel): oscuro dentro, una mancha de sol en el suelo de la entrada y la salida iluminada.

## Fidelidad
16. Las piezas reconocibles (fuente, portal, arco) se dibujan a partir de fotos de referencia, con sus proporciones medidas.
17. Los detalles de superficie (metralla) respetan los huecos: nunca sobre puertas ni ventanas, y se hacen más ralos lejos del foco.
18. Se puede cambiar la realidad para el juego (un portón convertido en bar) si da sitio a la historia.

## Proceso
19. Primero un boceto de líneas con la cámara bien calculada, después la generación por partes al estilo de la cripta.
20. El color se decide al final: la versión original puede quedar sosa, así que se añaden sombras y acentos de color para que el sitio resulte atractivo.
21. El "estilo" se define con números medibles: tamaño de la paleta y sus rampas, contornos, tamaño mínimo de mancha, tramado, contraste, luz y tonos por material. Así se puede transferir a otra paleta y comprobar el resultado.
