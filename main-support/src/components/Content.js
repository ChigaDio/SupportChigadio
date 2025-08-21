import React from 'react';
import { Typography, Box, Grid, Card, CardContent, Toolbar } from '@mui/material';
import EnumIdGrid from './EnumIdGrid';

function Content({ selectedMenu }) {
  return (
    <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
      <Toolbar />
      {selectedMenu === 'Main' && (
        <>
          <Typography variant="h4" gutterBottom>
            Welcome to Dashboard
          </Typography>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h5">Card 1</Typography>
                  <Typography>Data or chart placeholder.</Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h5">Card 2</Typography>
                  <Typography>More information.</Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </>
      )}
      {selectedMenu === 'Enum-ID' && <EnumIdGrid />}
      {selectedMenu === 'ClassData' && (
        <Typography variant="h4">ClassData Content (Placeholder)</Typography>
      )}
      {selectedMenu === 'State' && (
        <Typography variant="h4">State Content (Placeholder)</Typography>
      )}
      {selectedMenu === 'About' && (
        <Typography variant="h4">About Content</Typography>
      )}
    </Box>
  );
}

export default Content;