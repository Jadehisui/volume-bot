# ss-linked-list

[![MIT Licence](https://badges.frapsoft.com/os/mit/mit.svg?v=103)](https://opensource.org/licenses/mit-license.php) [![npm version](https://badge.fury.io/js/ss-linked-list.svg)](https://badge.fury.io/js/ss-linked-list)

Data Structure Serial -  Linked List 

 - written in Typescript, with generics type templating
 - support for iterator and iterable protocols.
 - support Singly-Linked List、Doubly-Linked List; and also Circle Singly or Doubly Linked List  
 - fully tested

Refer:
 - [前端学数据结构 - 链表（Linked List）](https://boycgit.github.io/ds-linked-list/)

## Installation

### Node.js / Browserify

```bash
npm install ss-linked-list --save
```

```javascript
var LinkedList = require('ss-linked-list');
```

### Global object

Include the pre-built script.

```html
<script src="./dist/index.umd.min.js"></script>

```

## Build & test

```bash
npm run build
```

```bash
npm test
```

## document

```bash
npm run doc
```

then open the generated `out/index.html` file in your browser.

## todo

Highly recommend article [面试精选：链表问题集锦](http://wuchong.me/blog/2014/03/25/interview-link-questions/) for more skils;

 - detect has loop or not，[Detect a loop in cyclic/circular linked list](https://js-algorithms.tutorialhorizon.com/2015/12/25/detect-cyclic-circular-linked-list/)，and then [count loop length](https://js-algorithms.tutorialhorizon.com/2015/12/26/loop-length-cyclic-circular-list/) 

## License

[MIT](LICENSE).
