import type {Replay,Ship} from './types';
export interface BoardState {turn:number;halite:Float64Array;ships:Record<string,Record<string,Ship>>;banks:Record<string,number>;dropoffs:{x:number;y:number;owner:number}[]}
export function normalizeReplay(replay:Replay):BoardState[]{
 const {width,height,grid}=replay.production_map;
 let cells=new Float64Array(width*height);grid.forEach((row,y)=>row.forEach((c,x)=>cells[y*width+x]=c.energy));
 let dropoffs:{x:number;y:number;owner:number}[]=[];
 const result:BoardState[]=[];
 // H3 stores ships at the START of each frame; banks/cells are at its END.
 // Frame t+1 therefore supplies the ships for the end-of-turn t display.
 const last=Math.max(0,replay.full_frames.length-2);
 for(let turn=0;turn<=last;turn++){
  const frame=replay.full_frames[turn];cells=cells.slice();
  for(const cell of frame.cells||[])cells[cell.y*width+cell.x]=cell.production;
  for(const event of frame.events||[])if(event.type==='construct'&&event.owner_id!==undefined)dropoffs=[...dropoffs,{...event.location,owner:event.owner_id}];
  result.push({turn,halite:cells,ships:replay.full_frames[turn+1]?.entities||{},banks:frame.energy||{},dropoffs:[...dropoffs]});
 }
 return result;
}
export function wrappedDistance(ax:number,ay:number,bx:number,by:number,w:number,h:number){const dx=Math.abs(ax-bx),dy=Math.abs(ay-by);return Math.min(dx,w-dx)+Math.min(dy,h-dy)}
