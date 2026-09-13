// STEP tessellation stays off the UI thread so quote choices remain responsive.
importScripts('/vendor/occt/occt-import-js.js');
self.onmessage = async ({data}) => {
  try {
    const occt = await occtimportjs({locateFile: name => '/vendor/occt/' + name});
    const result = occt.ReadStepFile(new Uint8Array(data), {
      linearUnit: 'millimeter', linearDeflectionType: 'bounding_box_ratio',
      linearDeflection: 0.002, angularDeflection: 0.5,
    });
    if (!result.success || !result.meshes?.length) throw new Error('No solid geometry could be read from this STEP file.');
    const meshes = result.meshes.map(m => ({
      position: new Float32Array(m.attributes.position.array),
      normal: m.attributes.normal ? new Float32Array(m.attributes.normal.array) : null,
      index: new Uint32Array(m.index.array),
    }));
    self.postMessage({meshes}, meshes.flatMap(m => [m.position.buffer, m.index.buffer, ...(m.normal ? [m.normal.buffer] : [])]));
  } catch (error) { self.postMessage({error: error.message}); }
};
