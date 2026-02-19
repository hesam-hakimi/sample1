import * as Mocha from 'mocha';

const mocha = new Mocha({ ui: 'bdd', color: true });
['pathSafety.test.js', 'mapping.test.js', 'search.test.js', 'indexParser.test.js'].forEach((f) => mocha.addFile(`${__dirname}/${f}`));

mocha.run((failures) => {
  process.exitCode = failures ? 1 : 0;
});
