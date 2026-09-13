/** Describe checked output, rather than the planner's proposed intent. */
export function describePreview(result, state) {
 const pv=result.preview,command=pv?.command||result.command;
 if(pv&&!pv.accepted)return 'This edit did not pass the checks. Your model is unchanged.';
 if(pv?.accepted&&command?.op==='sequence')return `${pv.step_outcomes.length} checked edits, applied together.${pv.invariants?.length?' Original hole surfaces stay fixed at every step.':''} Review each step below; one Undo restores the original.`;
 if(pv?.accepted&&pv.selection?.region){
  const axis=command.axis.toUpperCase();
  if(command.op==='translate'){
   const trials=pv.repair_trials||pv.checks?.find(c=>c.name==='repair_trials')?.detail||[];
   const strategy=trials.find(t=>t.accepted)?.strategy;
   if(strategy?.startsWith('interior_transition_'))return `The section moves up to ${Math.abs(command.amount_mm)} mm in the ${command.amount_mm<0?'negative':'positive'} ${axis} direction, tapering toward its boundary. Outside vertices stay fixed. Review the transition before applying.`;
   if(strategy==='sharp')return `Selected vertices move ${Math.abs(command.amount_mm)} mm in the ${command.amount_mm<0?'negative':'positive'} ${axis} direction. Outside vertices stay fixed.`;
   return 'The section edit passed its checks. Review the geometry and operation details before applying.';
  }
  if(command.op==='resize')return `The selected vertices span ${command.target_mm} mm along ${axis}. Outside vertices stay fixed.`;
 }
 if(pv?.accepted&&['drill_blind_hole','drill_surface_hole'].includes(command?.op)){
  const correction=pv.created_features?.find(f=>f.kind==='surface_blind_hole')?.precision_normalization_mm||0;
  return `A ${(2*command.radius_mm).toFixed(2)} mm diameter hole, ${command.depth_mm.toFixed(2)} mm deep from the selected surface. The floor remains closed.${correction>1e-10?` Local precision correction: up to ${correction.toExponential(2)} mm.`:''}`;
 }
 if(pv?.accepted&&command?.op==='counterbore')return `A ${(2*command.radius_mm).toFixed(2)} mm diameter recess, ${command.depth_mm.toFixed(2)} mm deep around the recognized hole. The lower bore remains open; review the annular shoulder before applying.`;
 if(pv?.accepted&&command?.op==='resize_preserving_holes'){
  const part=state.parts.find(p=>p.id===pv.selection?.part_id),axis={x:0,y:1,z:2}[command.axis],old=part.bounds[1][axis]-part.bounds[0][axis];
  return `${['Width','Depth','Height'][axis]} changes from ${old.toFixed(2)} to ${command.target_mm.toFixed(2)} mm. All ${pv.protected_features.length} hole profiles stay in place.`;
 }
 return result.explanation||'Your edit is ready to review.';
}
