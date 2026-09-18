interface ActivityNode {
  id: number;
  name: string;
  children: ActivityNode[];
}

interface TreeStructure {
  [municipality: string]: ActivityNode[];
}

interface ActivityRelationship {
  municipality: string;
  child_id: number;
  child_name: string;
  id: number;
  name: string;
}

interface ActivityDetail {
  municipality: string;
  id: number;
  parent_id: number | null;
  active: number;
}

interface ActivityWithRelationships {
  name: string;
  child_relationships: ActivityRelationship[];
  activity_details: ActivityDetail[];
}

interface CompleteActivityData {
  all_activity_details: { [key: number]: { name: string, municipality: string, parent_id: number | null, active: number } };
  parent_child_map: { [key: number]: Array<{ id: number, name: string, municipality: string }> };
}

export function buildActivityTree(activity: ActivityWithRelationships, completeData: CompleteActivityData): TreeStructure {
  const trees: TreeStructure = {};
  
  // Get all municipalities involved in this activity
  const municipalities = [...new Set([
    ...activity.child_relationships.map((rel) => rel.municipality),
    ...activity.activity_details.map((detail) => detail.municipality)
  ])];
  
  // Helper function to recursively build children for a node
  function buildChildren(nodeId: number, municipality: string): ActivityNode[] {
    const children: ActivityNode[] = [];
    const directChildren = completeData.parent_child_map[nodeId] || [];
    
    for (const child of directChildren) {
      if (child.municipality === municipality) {
        const childNode: ActivityNode = {
          id: child.id,
          name: child.name,
          children: buildChildren(child.id, municipality) // Recursive call for grandchildren
        };
        children.push(childNode);
      }
    }
    
    children.sort((a, b) => a.name.localeCompare(b.name));
    return children;
  }
  
  for (const municipality of municipalities) {
    const rootNodes: ActivityNode[] = [];
    
    // Get all activity instances for this municipality that belong to the current activity
    const mainActivityDetails = activity.activity_details.filter((detail) => 
      detail.municipality === municipality
    );
    
    for (const detail of mainActivityDetails) {
      const rootNode: ActivityNode = {
        id: detail.id,
        name: activity.name,
        children: buildChildren(detail.id, municipality)
      };
      rootNodes.push(rootNode);
    }
    
    // Remove duplicates and sort
    const uniqueRoots = rootNodes.filter((node, index, self) => 
      index === self.findIndex(n => n.id === node.id)
    );
    
    uniqueRoots.sort((a, b) => a.name.localeCompare(b.name));
    trees[municipality] = uniqueRoots;
  }
  
  return trees;
}

export function renderTreeNode(node: ActivityNode, depth: number = 0, isLast: boolean = true, prefix: string = ''): string {
  const connector = isLast ? '└── ' : '├── ';
  const newPrefix = prefix + (isLast ? '    ' : '│   ');
  
  let result = `${prefix}${connector}${node.name} (ID: ${node.id})\n`;
  
  node.children.forEach((child, index) => {
    const childIsLast = index === node.children.length - 1;
    result += renderTreeNode(child, depth + 1, childIsLast, newPrefix);
  });
  
  return result;
}

export function renderTree(roots: ActivityNode[]): string {
  if (roots.length === 0) return 'No activities found';
  
  let result = '';
  roots.forEach((root, index) => {
    const isLast = index === roots.length - 1;
    result += renderTreeNode(root, 0, isLast);
  });
  
  return result.trim();
}