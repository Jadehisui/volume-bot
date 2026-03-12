# cc-graph
Data Structure Serial -  Graph

 - written in Typescript
 - fully tested


## Installation

### Node.js / Browserify

```bash
npm install cc-graph --save
```

```javascript
var {Graph, GraphEdge, GraphVertex} = require('cc-graph');
```

### Global object

Include the pre-built script.

```html
<script src="./dist/index.umd.min.js"></script>

```

## usage

```js
const graph = new Graph();

const vertexA = new GraphVertex('A');
const vertexB = new GraphVertex('B');
const vertexC = new GraphVertex('C');
const vertexD = new GraphVertex('D');

const edgeAB = new GraphEdge(vertexA, vertexB, 1);
const edgeBC = new GraphEdge(vertexB, vertexC, 2);
const edgeCD = new GraphEdge(vertexC, vertexD, 3);
const edgeAD = new GraphEdge(vertexA, vertexD, 4);

graph
    .addEdge(edgeAB)
    .addEdge(edgeBC)
    .addEdge(edgeCD)
    .addEdge(edgeAD);

expect(graph.getWeight()).toBe(10);
```

## Build & test

```bash
npm run build
```

```bash
npm test
```

## Document

```bash
npm run doc
```

then open the generated `out/index.html` file in your browser.

## Why cc-graph
There is a redundant `debugger` in the graph.ts. It's seriously affect the normal use, i submit one PR but nobody reply me. So i fork a new repo and renamed cc-graph.


## License

[MIT](LICENSE).
